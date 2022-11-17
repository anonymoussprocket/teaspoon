# Reference implementation of the Trustless Staking Token for Tezos
# Written using SmartPy (https://smartpy.io/ide)
# Mike Radin
# 2022, May; version 2.5

import smartpy as sp

BalanceTransferType = sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value")))
BalanceMintType = sp.TRecord(destination = sp.TAddress, amount = sp.TNat).layout(("destination", "amount"))
BalanceBurnType = sp.TRecord(source = sp.TAddress, amount = sp.TNat).layout(("source", "amount"))
SetShareType = sp.TRecord(account = sp.TAddress, amount = sp.TNat).layout(("account", "amount"))
RegisterShareType = sp.TRecord(account = sp.TAddress, amount = sp.TNat).layout(("account", "amount"))

DELEGATE_THRESHOLD = 650000
MINIMUM_DEPOSIT = 10000000
MINIMUM_GUARANTEE = 1000000

class Instrument(sp.Contract):
    def __init__(self, deployer, schedule, duration, interval, periods, start):
        self.init(
            deployer = deployer,
            schedule = schedule,
            duration = duration,
            interval = interval,
            periods = periods,
            start = start,
            freeCollateral = sp.mutez(0),
            depositedCollateral = sp.mutez(0),
            balance_token = deployer,
            share_token = deployer,
            guarantors = sp.list([], t = sp.TAddress)
        )

    @sp.entry_point
    def bootstrap(self, params):
        sp.set_type(params.balance_token, sp.TAddress)
        sp.set_type(params.share_token, sp.TAddress)

        sp.verify(sp.sender == self.data.deployer, message = "Invalid request")
        sp.verify(self.data.deployer == self.data.balance_token, message = "Already bootstrapped")

        BalanceBootstrapReference = sp.contract(sp.TAddress, params.balance_token, entry_point="bootstrap").open_some()
        sp.transfer(sp.self_address, sp.tez(0), BalanceBootstrapReference)

        ShareBootstrapReference = sp.contract(sp.TAddress, params.share_token, entry_point="bootstrap").open_some()
        sp.transfer(sp.self_address, sp.tez(0), ShareBootstrapReference)

        self.data.balance_token = params.balance_token
        self.data.share_token = params.share_token
        self.data.deployer = sp.address('tz1Ke2h7sDdakHJQh8WX4Z372du1KChsksyU')

    @sp.entry_point
    def registerShare(self, params):
        sp.set_type(params.account, sp.TAddress)
        sp.set_type(params.amount, sp.TNat)

        sp.verify(sp.sender == self.data.share_token, message = "Invalid call")

        removeGuarantor = sp.local('removeGuarantor', False)
        newGuarantor = sp.local('newGuarantor', True)
        sp.for guarantor in self.data.guarantors:
            sp.if (guarantor == params.account):
                sp.if (params.amount > sp.nat(0)):
                    newGuarantor.value = False
                sp.else:
                    removeGuarantor.value = True

        sp.if (removeGuarantor.value == True):
            reducedGuarantors = sp.local('reducedGuarantors', sp.list([], t = sp.TAddress))
            sp.for guarantor in self.data.guarantors:
                sp.if (guarantor == sp.sender):
                    pass
                sp.else:
                    reducedGuarantors.value.push(guarantor)
            self.data.guarantors = reducedGuarantors.value
        sp.else:
            pass

        sp.if (newGuarantor.value == True):
            self.data.guarantors.push(params.account)
        sp.else:
            pass

    @sp.entry_point
    def default(self):
        sp.verify(self.data.deployer != self.data.balance_token, message = "Not bootstrapped")

        self.data.freeCollateral += sp.amount
        self.data.depositedCollateral += sp.amount

    @sp.entry_point
    def deposit(self):
        sp.verify(sp.amount > sp.mutez(0), message = "Deposit too low")
        period = self.getPeriod()

        tokenBalance = sp.local('tokenBalance', 0)
        requiredCollateral = sp.local('requiredCollateral', sp.tez(0))
        expectedReturn = sp.ediv(sp.amount, self.data.schedule[period])
        coins = sp.ediv(sp.amount, sp.tez(1))
        sp.if (expectedReturn.is_some()) & (coins.is_some()):
            tokenBalance.value = sp.fst(expectedReturn.open_some())
            wholeCoins = sp.fst(coins.open_some()) # TODO: this makes the token have 0 decimals
            sp.verify(tokenBalance.value > wholeCoins, message = "Deposit too low")
            requiredCollateral.value = sp.utils.nat_to_tez(sp.as_nat(tokenBalance.value - wholeCoins))

        sp.verify(requiredCollateral.value <= self.data.freeCollateral, message = "Insufficient collateral")

        self.data.freeCollateral -= requiredCollateral.value

        BalanceMintReference = sp.contract(BalanceMintType, self.data.balance_token, entry_point="mint").open_some()
        mint = sp.record(destination = sp.sender, amount = tokenBalance.value)
        mint = sp.set_type_expr(mint, BalanceMintType)
        sp.transfer(mint, sp.tez(0), BalanceMintReference)

    @sp.entry_point
    def redeem(self, amount):
        sp.set_type(amount, sp.TNat)

        currentBalance = sp.view("getBalance", self.data.balance_token, sp.sender).open_some("Incompatible view")
        sp.verify(currentBalance >= amount, "Insufficient balance")

        currentPeriod = sp.local('currentPeriod', self.getPeriod())

        self.redeemBalance(sp.sender, currentPeriod.value, amount)

    # proposalActive
    # proposalList

    # @sp.entry_point
    # def proposeDelegate(self, delegate):
    #     pass
    #     sp.level

    @sp.entry_point
    def setDelegate(self, delegate):
        sp.set_type(delegate, sp.TOption(sp.TKeyHash))

        sp.verify(self.verifyGuarantor(sp.sender), message = "Not a guarantor")

        currentShare = sp.local('currentShare', sp.nat(0))
        currentShare.value = sp.view("getBalance", self.data.share_token, sp.sender).open_some("Incompatible view")

        sp.if (currentShare.value >= DELEGATE_THRESHOLD):
            sp.set_delegate(delegate)
        sp.else:
            pass

    @sp.entry_point
    def terminate(self, depositors):
        sp.set_type(depositors, sp.TList(sp.TAddress))

        currentPeriod = sp.local('currentPeriod', self.getPeriod())
        sp.verify(self.verifyGuarantor(sp.sender), message = "Not a guarantor")
        sp.verify(currentPeriod.value == self.data.periods, message = "Validity period not complete")

        currentBalance = sp.local('currentBalance', sp.nat(0))
        sp.for depositor in depositors:
            currentBalance.value = sp.view("getBalance", self.data.balance_token, depositor).open_some("Incompatible view")

            sp.if (currentBalance.value > sp.nat(0)):
                self.redeemBalance(depositor, currentPeriod.value, currentBalance.value)
            sp.else:
                pass

    @sp.entry_point
    def depositCollateral(self):
        totalShares = sp.local('totalShares', sp.nat(0))
        totalShares.value = sp.view("getTotalSupply", self.data.share_token, sp.unit).open_some("Incompatible view")

        shareIssue = sp.local('shareIssue', sp.nat(0))

        sp.if (totalShares.value == 0) & (sp.len(self.data.guarantors) == 0):
            shareIssue.value = sp.utils.mutez_to_nat(sp.amount)

            self.data.guarantors.push(sp.sender)
        sp.else:
            sp.if (totalShares.value > 0) & (sp.len(self.data.guarantors) > 0):
                numerator = sp.local('numerator', sp.nat(0))
                numerator.value = sp.utils.mutez_to_nat(self.data.depositedCollateral + sp.amount)
                numerator.value = numerator.value * totalShares.value

                shareIssue.value = sp.as_nat(sp.fst(sp.ediv(numerator.value, sp.utils.mutez_to_nat(self.data.depositedCollateral)).open_some()) - totalShares.value)

                sp.if ~self.verifyGuarantor(sp.sender):
                    self.data.guarantors.push(sp.sender)
                sp.else:
                    pass
            sp.else:
                sp.failwith('Inconsistent token state')

        ShareMintReference = sp.contract(BalanceMintType, self.data.share_token, entry_point="mint").open_some()
        mint = sp.record(destination = sp.sender, amount = shareIssue.value)
        mint = sp.set_type_expr(mint, BalanceMintType)
        sp.transfer(mint, sp.tez(0), ShareMintReference)

        self.data.freeCollateral += sp.amount
        self.data.depositedCollateral += sp.amount

    @sp.entry_point
    def withdrawCollateral(self, amount): # TODO: amount should be mutez
        sp.set_type(amount, sp.TNat)

        totalShares = sp.local('totalShares', sp.nat(0))
        totalShares.value = sp.view("getTotalSupply", self.data.share_token, sp.unit).open_some("Incompatible view")

        requiredShare = sp.local('requiredShare', sp.nat(0))
        requiredShare.value = sp.utils.mutez_to_nat(sp.split_tokens(sp.utils.nat_to_mutez(amount), totalShares.value, sp.utils.mutez_to_nat(self.data.freeCollateral)))

        currentShare = sp.local('currentShare', sp.nat(0))
        currentShare.value = sp.view("getBalance", self.data.share_token, sp.sender).open_some("Incompatible view")

        sp.verify(currentShare.value > sp.nat(0), message = "Not a guarantor")
        sp.verify(requiredShare.value <= currentShare.value, message = "Insufficient share")

        share = sp.split_tokens(self.data.freeCollateral, requiredShare.value, totalShares.value)
        sp.verify(share >= sp.utils.nat_to_mutez(sp.as_nat(amount - sp.nat(10))), message = "Requested amount exceeds total share") # TODO: rounding error "- 10"
        sp.verify(sp.utils.nat_to_mutez(amount) <= self.data.freeCollateral, message = "Insufficient free collateral")

        ShareBurnReference = sp.contract(BalanceBurnType, self.data.share_token, entry_point="burn").open_some()
        burn = sp.record(source = sp.sender, amount = requiredShare.value)
        burn = sp.set_type_expr(burn, BalanceBurnType)
        sp.transfer(burn, sp.tez(0), ShareBurnReference)

        self.data.freeCollateral -= sp.utils.nat_to_mutez(amount)
        self.data.depositedCollateral -= sp.utils.nat_to_mutez(amount)

        sp.if sp.as_nat(currentShare.value - requiredShare.value) == 0:
            reducedGuarantors = sp.local('reducedGuarantors', sp.list([], t = sp.TAddress))
            sp.for guarantor in self.data.guarantors:
                sp.if (guarantor == sp.sender):
                    pass
                sp.else:
                    reducedGuarantors.value.push(guarantor)
            self.data.guarantors = reducedGuarantors.value
        sp.else:
            pass

        sp.send(sp.sender, sp.utils.nat_to_mutez(amount))

        # TODO: deal with dust and "late" reward deposits

    @sp.onchain_view(pure=True)
    def getGuarantorRedeemableValue(self, guarantor):
        sp.set_type(guarantor, sp.TAddress)

        currentShare = sp.local('currentShare', sp.nat(0))
        currentShare.value = sp.view("getBalance", self.data.share_token, guarantor).open_some("Incompatible view")

        totalShares = sp.local('totalShares', sp.nat(0))
        totalShares.value = sp.view("getTotalSupply", self.data.share_token, sp.unit).open_some("Incompatible view")
        
        currentGuarantorBalance = sp.split_tokens(self.data.freeCollateral, currentShare.value, totalShares.value)
        sp.result(currentGuarantorBalance)

    @sp.onchain_view(pure=True)
    def getGuaranteeRedeemableValue(self, amount): # TODO: rename amount since it's number of shares, not xtz
        sp.set_type(amount, sp.TNat)

        totalShares = sp.local('totalShares', sp.nat(0))
        totalShares.value = sp.view("getTotalSupply", self.data.share_token, sp.unit).open_some("Incompatible view")

        sp.verify(amount <= totalShares.value, message = "Invalid guarantee share")

        currentGuarantorBalance = sp.split_tokens(self.data.freeCollateral, amount, totalShares.value)
        sp.result(currentGuarantorBalance)

    @sp.onchain_view(pure=True)
    def getDepositorRedeemableValue(self, depositor):
        sp.set_type(depositor, sp.TAddress)

        result = sp.view("getBalance", self.data.balance_token, depositor).open_some("Incompatible view")
        currentBalance = result

        currentPeriod = sp.local('currentPeriod', self.getPeriod())

        sp.result(sp.split_tokens(self.data.schedule[currentPeriod.value], currentBalance, 1))

    @sp.onchain_view(pure=True)
    def getDepositRedeemableValue(self, amount):
        sp.set_type(amount, sp.TNat)

        currentPeriod = sp.local('currentPeriod', self.getPeriod())

        sp.result(sp.split_tokens(self.data.schedule[currentPeriod.value], amount, 1))

    def getPeriod(self):
        y = sp.local('y', self.data.periods)
        sp.if sp.now > self.data.start.add_seconds(sp.to_int(self.data.duration)):
            y.value = self.data.periods
        sp.else:
            ttm = sp.as_nat(self.data.duration - sp.as_nat(sp.now - self.data.start))
            y.value = sp.as_nat(self.data.periods - (ttm // self.data.interval) - 1)
        return y.value

    def verifyGuarantor(self, account):
        isGuarantor = sp.local('isGuarantor', False)
        sp.for guarantor in self.data.guarantors:
            sp.if (guarantor == account):
                isGuarantor.value = True
            sp.else:
                pass

        return isGuarantor.value

    def redeemBalance(self, depositor, currentPeriod, currentBalance):
        sp.set_type(depositor, sp.TAddress)
        sp.set_type(currentPeriod, sp.TNat)
        sp.set_type(currentBalance, sp.TNat)

        xtzBalance = sp.split_tokens(self.data.schedule[currentPeriod], currentBalance, 1)
        releasedCollateral = sp.split_tokens(sp.tez(1) - self.data.schedule[currentPeriod], currentBalance, 1)

        self.data.freeCollateral += releasedCollateral

        BalanceBurnReference = sp.contract(BalanceBurnType, self.data.balance_token, entry_point="burn").open_some()
        burn = sp.record(source = depositor, amount = currentBalance)
        burn = sp.set_type_expr(burn, BalanceBurnType)
        sp.transfer(burn, sp.tez(0), BalanceBurnReference)

        sp.send(depositor, xtzBalance)
