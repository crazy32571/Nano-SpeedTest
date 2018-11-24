import logging
import random
import requests
import time
from decimal import *

from django.conf import settings as settings
import nano

from .. import models as models
from .wallets import *
from .nodes import *
from .accounts import *
from ._pow import POWService
from ._nodetiming import *


logger = logging.getLogger(__name__)

class AccountBalanceMismatchException(Exception):
    def __init__(self, balance_actual, balance_db, account):
        Exception.__init__(self, "{0} != {1} for account: {2}".format(balance_actual, balance_db, account))

class InsufficientNanoException(Exception):
    def __init__(self):
        Exception.__init__(self, "The Nano account did not have enough RAW to make a transaction.")

class AddressDoesNotExistException(Exception):
    def __init__(self, account, wallet):
        Exception.__init__(self, "The Nano address {0} does not exist on wallet {1}".format(account, wallet))

class NoIncomingBlocksException(Exception):
    def __init__(self, account):
        Exception.__init__(self, "There were no incoming blocks to receive for the account: %s." % account)

class TooManyIncomingBlocksException(Exception):
    def __init__(self, account):
        Exception.__init__(self, "There were more than one incoming blocks for the account: %s." % account)

class InvalidPOWException(Exception):
    def __init__(self):
        Exception.__init__(self, "The POW on the account was not valid.")

class NoAccountsException(Exception):
    def __init__(self, node='NA'):
        Exception.__init__(self, "The specified node (%s) does not have any accounts." % node)


def new_transaction_random(batch):
    """
    Create a new transaction with random origin, destination, and amount fields.
    This does not execute the transaction on the nano network.

    @param batch: Batch this transaction is a part of
    @return: New transaction object
    """

    accounts_list = get_accounts(in_use=False)

    if len(accounts_list) == 0:
        raise NoAccountsException()

    origin = random.choice(accounts_list)

    account_destinations = []

    for account in accounts_list:
        if account.wallet.node.id != origin.wallet.node.id:
            account_destinations.append(account)

    if len(account_destinations) == 0:
        raise NoAccountsException()

    destination = random.choice(account_destinations)

    base_amount = 100000000000000000000
    amount = base_amount * Decimal(random.randint(1, 9))

    return new_transaction(origin_account=origin, destination_account=destination, amount=amount, batch=batch)

def new_transaction_nodes(origin_node, destination_node, batch):
    """
    Create a transaction from the given properties.

    @param origin_node: Node source
    @param destination_node: Node receiver
    @param batch: Batch of the new transaction
    @return: New transaction object
    """

    origin_accounts_list = get_accounts(node=origin_node, in_use=False)
    destination_accounts_list = get_accounts(node=destination_node, in_use=False)

    if len(origin_accounts_list) == 0:
        raise NoAccountsException(origin_node)
    
    if len(destination_accounts_list) == 0:
        raise NoAccountsException(destination_node)

    origin = random.choice(origin_accounts_list)

    if destination_accounts_list.filter(address=origin.address).exists():
        destination_accounts_list = destination_accounts_list.exclude(address=origin.address)

    destination = random.choice(destination_accounts_list)

    base_amount = 100000000000000000000
    amount = base_amount * Decimal(random.randint(1, 9))

    return new_transaction(origin_account=origin, destination_account=destination, amount=amount, batch=batch)

def new_transaction(origin_account, destination_account, amount, batch):
    """
    Create a transaction from the given properties.
    We must lock accounts on creation of transaction between them.

    @param origin_account: Account source
    @param destination_account: Account receiver
    @param amount: Amount in RAW to send
    @param batch: Batch of the transaction
    @return: New transaction object
    """

    transaction = models.Transaction(
        origin=origin_account,
        destination=destination_account,
        amount=amount,
        batch=batch
    )

    ##Lock origin and destination accounts
    ##Unlock accounts
    origin_account.lock()
    destination_account.lock()

    transaction.save()
    return transaction

def send_transaction(transaction):
    """
    Complete a transaction on the Nano network while timing results.
    We must unlock accounts on any failure or at completion of sending.

    @param transaction: Transaction to execute
    @return: Transaction object with new information
    @raise: RPCException: RPC Failure
    @raise: AccountBalanceMismatchException: Will prevent the execution of the current transaction but will also rebalance the account
    @raise: InsufficientNanoException: The origin account does not have enough funds
    @raise: InvalidPOWException: The origin account does not have valid POW
    @raise: NoIncomingBlocksException: Incoming block not found on destination node. This will lead to invalid POW and balance in the destination account if not handled
    @raise: TooManyIncomingBlocksException: Incoming block not found on destination node. This will lead to invalid POW and balance in the destination account if not handled
    """

    rpc_origin_node = nano.rpc.Client(transaction.origin.wallet.node.URL)
    rpc_destination_node = nano.rpc.Client(transaction.destination.wallet.node.URL)

    # Do some origin balance checking
    origin_balance = rpc_origin_node.account_balance(account=transaction.origin.address)['balance']
    if (origin_balance != transaction.origin.current_balance):
        transaction.origin.current_balance = origin_balance
        transaction.origin.save()
        transaction.save()

        ##Unlock accounts
        transaction.origin.unlock()
        transaction.destination.unlock()

        raise AccountBalanceMismatchException(
            balance_actual=origin_balance, 
            balance_db=transaction.origin.current_balance,
            account=transaction.origin.address
        )
    elif (origin_balance - transaction.amount <= 0):
        ##Unlock accounts
        transaction.origin.unlock()
        transaction.destination.unlock()
        raise InsufficientNanoException()
    
    # Make sure the wallet contains the account address
    if (not rpc_origin_node.wallet_contains(wallet=transaction.origin.wallet.wallet_id, account=transaction.origin.address)):
        ##Unlock accounts
        transaction.origin.unlock()
        transaction.destination.unlock()
        raise AddressDoesNotExistException(
            wallet=transaction.origin.wallet,
            account=transaction.origin.address
        )
    
    if (not rpc_destination_node.wallet_contains(wallet=transaction.destination.wallet.wallet_id, account=transaction.destination.address)):
        ##Unlock accounts
        transaction.origin.unlock()
        transaction.destination.unlock()
        raise AddressDoesNotExistException(
            wallet=transaction.destination.wallet,
            account=transaction.destination.address
        )

    # Make sure the POW is there (not in the POW regen queue)
    if not transaction.origin.POW:
        try:
            frontier = rpc_origin_node.frontiers(account=transaction.origin.address, count=1)[transaction.origin.address]
            POWService.enqueue_account(address=transaction.origin.address, frontier=frontier)
            logger.info('Generated PoW during sending for: %s' % transaction.origin.address)
        except Exception as e:
            ##Unlock accounts
            transaction.origin.unlock()
            transaction.destination.unlock()
            logger.error('Error adding address, frontier pair to POWService: %s' % e)

        ##Unlock accounts
        transaction.origin.unlock()
        transaction.destination.unlock()
        logger.warning('Transaction origin POW is invalid, transaction.id: %s' % str(transaction.id))
        raise InvalidPOWException()
    
    if transaction.destination.POW is None:
        # We ignore this if we are sending a first block
        # POWService.enqueue_account(transaction.destination)
        # raise InvalidPOWException()
        pass

    # Start the timestamp before we try to send out the request
    transaction.start_send_timestamp = int(round(time.time() * 1000))

    try:
        # After this call, the nano will leave the origin
        transaction.transaction_hash_sending = rpc_origin_node.send(
            wallet=transaction.origin.wallet.wallet_id,
            source=transaction.origin.address,
            destination=transaction.destination.address,
            amount=int(transaction.amount),
            work=transaction.origin.POW,
            id=transaction.id
        )


        # Update the balances and POW
        transaction.origin.current_balance = transaction.origin.current_balance - transaction.amount
        transaction.destination.current_balance = transaction.destination.current_balance + transaction.amount
        transaction.origin.POW = None

    except nano.rpc.RPCException as e:
        logger.error(e)
        ##Unlock accounts
        transaction.origin.unlock()
        transaction.destination.unlock()
        raise nano.rpc.RPCException()
    
    # Handover control to the timing service (expecting the timestamp to be set on return)
    try:
        time_transaction_send(transaction)
    except Exception as e:
        ##Unlock accounts
        transaction.origin.unlock()
        transaction.destination.unlock()
        logger.error('Transaction timing_send failed, transaction.id: %s, error: %s' % (str(transaction.id), str(e)))

    transaction.origin.save()
    transaction.destination.save()
    transaction.save()

    max_retries = 120
    incoming_blocks = None

    while (incoming_blocks is None or len(incoming_blocks) == 0) and max_retries > 0:
        rpc_origin_node.republish(hash=transaction.transaction_hash_sending)
        try:
            rpc_destination_node.search_pending_all()
            incoming_blocks = rpc_destination_node.pending(account=transaction.destination.address)
        except nano.rpc.RPCException:
            logger.error('Transaction send failure, transaction.id: %s' % str(transaction.id))
            ##Unlock accounts
            transaction.origin.unlock()
            transaction.destination.unlock()
            raise nano.rpc.RPCException()
        
        max_retries = max_retries - 1

        time.sleep(0.25)

    # We need to set POW to None because it will be no longer valid as the node will eventually accept the block(s) (if they are unopened?)
    if not incoming_blocks or not len(incoming_blocks):
        transaction.destination.POW = None
        transaction.destination.save()
        transaction.save()
        logger.error('No Incoming blocks, transaction.id: %s' % str(transaction.id))

        ##Unlock accounts
        transaction.origin.unlock()
        transaction.destination.unlock()
        raise NoIncomingBlocksException(transaction.destination.address)
    elif len(incoming_blocks) > 1:
        transaction.destination.POW = None
        transaction.destination.save()
        transaction.save()

        ##Unlock accounts
        transaction.origin.unlock()
        transaction.destination.unlock()
        raise TooManyIncomingBlocksException(transaction.destination.address)

    for block_hash in incoming_blocks:
        transaction.start_receive_timestamp = int(round(time.time() * 1000))

        try:
            transaction.transaction_hash_receiving = rpc_destination_node.receive(
                wallet=transaction.destination.wallet.wallet_id,
                account=transaction.destination.address,
                block=block_hash,
                work=transaction.destination.POW
            )
        except nano.rpc.RPCException:
            ##Unlock accounts
            transaction.origin.unlock()
            transaction.destination.unlock()
            raise nano.rpc.RPCException()
    
    # Handover control to the timing service (expecting the timestamp to be set on return)
    try:
        time_transaction_receive(transaction)
    except Exception as e:
        ##Unlock accounts
        transaction.origin.unlock()
        transaction.destination.unlock()
        logger.error('Transaction timing_receive failed, transaction.id: %s, error: %s' % (str(transaction.id), str(e)))

    transaction.destination.POW = None

    transaction.destination.save()
    transaction.save()

    # Regenerate POW on the accounts
    POWService.enqueue_account(address=transaction.origin.address, frontier=transaction.transaction_hash_sending)
    POWService.enqueue_account(address=transaction.destination.address, frontier=transaction.transaction_hash_receiving)

    ##Unlock accounts
    transaction.origin.unlock()
    transaction.destination.unlock()

    return transaction

def get_transactions(enabled=True, batch=None):
    """
    Get all transactions in the database.

    @param enabled: Get transactions whose origin and destination node is enabled
    @param batch: If not None, only get transactions within a batch (precedence)
    @return: Query of all transactions
    """

    if batch is not None:
        return models.Transaction.objects.filter(batch__id=batch.id)

    if enabled:
        return models.Transaction.objects.filter(origin__wallet__node__enabled=enabled, destination__wallet__node__enabled=enabled)
    
    return models.Transaction.objects.all()


def get_recent_transactions(count=25):
    """
    Get most recent count transaction with enabled nodes

    @param count: Number of most recent transactions to return
    @return: Query of transactions
    """
    return models.Transaction.objects.select_related()[:count]


def get_transaction(id):
    """
    Get a transaction by id

    @param id: Id of the transaction to search for
    @return: None if not found or Transaction object
    @raise: MultipleObjectsReturned: If more than one object exists, this is raised
    """

    try:
        return models.Transaction.objects.get(id=id)
    except models.Transaction.DoesNotExist:
        return None
    except MultipleObjectsReturned:
        raise MultipleObjectsReturned()