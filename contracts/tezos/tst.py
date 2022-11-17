# Reference implementation of the Trustless Staking Token for Tezos
# Written using SmartPy (https://smartpy.io/ide)
# Mike Radin
# 2022, May; version 2.3

import smartpy as sp

BalanceTransferType = sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value")))
BalanceMintType = sp.TRecord(destination = sp.TAddress, amount = sp.TNat).layout(("destination", "amount"))
BalanceBurnType = sp.TRecord(source = sp.TAddress, amount = sp.TNat).layout(("source", "amount"))

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
            balance_token = deployer,
            collateral = sp.big_map(tkey = sp.TAddress, tvalue = sp.TNat),
            guarantors = sp.list([], t = sp.TAddress)
        )

    @sp.entry_point
    def bootstrap(self, _balance_token):
        sp.set_type(_balance_token, sp.TAddress)

        sp.verify(sp.sender == self.data.deployer, message = "Invalid request")
        sp.verify(self.data.deployer == self.data.balance_token, message = "Already bootsrapped")

        BalanceBootstrapReference = sp.contract(sp.TAddress, _balance_token, entry_point="bootstrap").open_some()
        sp.transfer(sp.self_address, sp.tez(0), BalanceBootstrapReference)

        self.data.balance_token = _balance_token
        self.data.deployer = sp.address('tz1Ke2h7sDdakHJQh8WX4Z372du1KChsksyU')

    @sp.entry_point
    def default(self):
        sp.verify(self.data.deployer != self.data.balance_token, message = "Not bootsrapped")

        self.data.freeCollateral += sp.amount

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

        xtzBalance = sp.split_tokens(self.data.schedule[currentPeriod.value], amount, 1)

        releasedCollateral = sp.split_tokens(sp.tez(1) - self.data.schedule[currentPeriod.value], amount, 1)

        self.data.freeCollateral += releasedCollateral

        remainingBalance = sp.as_nat(currentBalance - amount)

        BalanceBurnReference = sp.contract(BalanceBurnType, self.data.balance_token, entry_point="burn").open_some()
        burn = sp.record(source = sp.sender, amount = amount)
        burn = sp.set_type_expr(burn, BalanceBurnType)
        sp.transfer(burn, sp.tez(0), BalanceBurnReference)

        sp.send(sp.sender, xtzBalance)

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

        sp.if (self.data.collateral[sp.sender] >= DELEGATE_THRESHOLD):
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
                xtzBalance = sp.split_tokens(self.data.schedule[currentPeriod.value], currentBalance.value, 1)
                releasedCollateral = sp.split_tokens(sp.tez(1) - self.data.schedule[currentPeriod.value], currentBalance.value, 1)

                self.data.freeCollateral += releasedCollateral

                BalanceBurnReference = sp.contract(BalanceBurnType, self.data.balance_token, entry_point="burn").open_some()
                burn = sp.record(source = depositor, amount = currentBalance.value)
                burn = sp.set_type_expr(burn, BalanceBurnType)
                sp.transfer(burn, sp.tez(0), BalanceBurnReference)

                sp.send(depositor, xtzBalance)
            sp.else:
                pass

    @sp.entry_point
    def depositCollateral(self):
        sp.if (sp.len(self.data.guarantors) == 0):
            self.data.guarantors.push(sp.sender)
            self.data.collateral[sp.sender] = sp.nat(1000000)
        sp.else:
            sp.if (self.data.collateral.get(sp.sender, default_value = sp.nat(0)) == sp.nat(1000000)):
                pass
            sp.else:
                self.rebalanceCollateralDeposit(sp.utils.mutez_to_nat(sp.amount))

        self.data.freeCollateral += sp.amount

    @sp.entry_point
    def withdrawCollateral(self, amount):
        sp.set_type(amount, sp.TNat)

        sp.verify(self.data.collateral.contains(sp.sender), message = "Not a guarantor")

        share = sp.split_tokens(self.data.freeCollateral, self.data.collateral[sp.sender], sp.nat(1000000))
        sp.verify(sp.utils.mutez_to_nat(share) >= amount, message = "Requested amount exceeds total share")
        sp.verify(sp.utils.nat_to_mutez(amount) <= self.data.freeCollateral, message = "Insufficient free collateral")

        self.rebalanceCollateralWithdrawal(amount)
        self.data.freeCollateral -= sp.utils.nat_to_mutez(amount)
        sp.send(sp.sender, sp.utils.nat_to_mutez(amount))
        # TODO: deal with dust

    @sp.onchain_view(pure=True)
    def getGuarantorRedeemableValue(self, guarantor):
        sp.set_type(guarantor, sp.TAddress)

        currentGuarantorBalance = sp.split_tokens(self.data.freeCollateral, self.data.collateral[guarantor], sp.nat(1000000))
        sp.result(currentGuarantorBalance)

    @sp.onchain_view(pure=True)
    def getGuaranteeRedeemableValue(self, amount):
        sp.set_type(amount, sp.TNat)

        sp.verify(amount <= sp.nat(1000000), message = "Invalid guarantee share")

        currentGuarantorBalance = sp.split_tokens(self.data.freeCollateral, amount, sp.nat(1000000))
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
            y.value = (sp.as_nat(self.data.periods) - (ttm // self.data.interval) - 1)
        return y.value

    def rebalanceCollateralDeposit(self, increase):
        sp.set_type(increase, sp.TNat)

        newCollateralBalance = sp.utils.mutez_to_nat(self.data.freeCollateral) + increase
        currentCollateralBalance = self.data.freeCollateral

        newGuarantor = sp.local('newGuarantor', True)
        sp.for guarantor in self.data.guarantors:
            currentGuarantorBalance = sp.split_tokens(currentCollateralBalance, self.data.collateral[guarantor], sp.nat(1000000))

            sp.if (guarantor != sp.sender):
                newGuarantorShare = sp.utils.mutez_to_nat(currentGuarantorBalance) * sp.nat(1000000) / newCollateralBalance
                self.data.collateral[guarantor] = newGuarantorShare
            sp.else:
                sp.if (self.data.collateral.contains(guarantor)):
                    newGuarantor.value = False

                newGuarantorBalance = sp.utils.mutez_to_nat(currentGuarantorBalance) + increase
                newGuarantorShare = newGuarantorBalance * sp.nat(1000000) / newCollateralBalance
                self.data.collateral[guarantor] = newGuarantorShare

        sp.if (newGuarantor.value):
            self.data.guarantors.push(sp.sender)

            newGuarantorShare = increase * sp.nat(1000000) / newCollateralBalance
            self.data.collateral[sp.sender] = newGuarantorShare

    def rebalanceCollateralWithdrawal(self, decrease):
        sp.trace('rebalanceCollateralWithdrawal')
        sp.trace(sp.sender)
        sp.set_type(decrease, sp.TNat)

        sp.trace('current, new')
        currentCollateralBalance = self.data.freeCollateral
        newCollateralBalance = sp.as_nat(sp.utils.mutez_to_nat(self.data.freeCollateral) - decrease)
        sp.trace(currentCollateralBalance)
        sp.trace(newCollateralBalance)

        removeGuarantor = sp.local('removeGuarantor', False)
        sp.for guarantor in self.data.guarantors:
            currentGuarantorBalance = sp.local('currentGuarantorBalance', sp.mutez(0))
            currentGuarantorBalance.value = sp.split_tokens(currentCollateralBalance, self.data.collateral[guarantor], sp.nat(1000000))

            sp.if (guarantor != sp.sender):
                newGuarantorShare = sp.utils.mutez_to_nat(currentGuarantorBalance.value) * sp.nat(1000000) / newCollateralBalance
                self.data.collateral[guarantor] = newGuarantorShare
            sp.else:
                sp.trace('is sender')
                newGuarantorBalance = sp.local('newGuarantorBalance', sp.as_nat(sp.utils.mutez_to_nat(currentGuarantorBalance.value) - decrease))
                sp.trace(currentGuarantorBalance.value)
                sp.trace(newGuarantorBalance.value)
                sp.if (newGuarantorBalance.value < sp.nat(20000)):
                    del self.data.collateral[guarantor]
                    removeGuarantor.value = True
                sp.else:
                    newGuarantorShare = newGuarantorBalance.value * sp.nat(1000000) / newCollateralBalance
                    self.data.collateral[guarantor] = newGuarantorShare

        sp.if (removeGuarantor.value):
            reducedGuarantors = sp.local('reducedGuarantors', sp.list([], t = sp.TAddress))
            sp.for guarantor in self.data.guarantors:
                sp.if (guarantor == sp.sender):
                    pass
                sp.else:
                    reducedGuarantors.value.push(guarantor)
            self.data.guarantors = reducedGuarantors.value

    def verifyGuarantor(self, account):
        isGuarantor = sp.local('isGuarantor', False)
        sp.for guarantor in self.data.guarantors:
            sp.if (guarantor == account):
                isGuarantor.value = True
            sp.else:
                pass

        return isGuarantor.value
