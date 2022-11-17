# Reference implementation of the Trustless Staking Token for Tezos
# Written using SmartPy (https://smartpy.io/ide)
# Mike Radin
# 2022, May; version 2.2

import smartpy as sp

DELEGATE_THRESHOLD = 650000
MINIMUM_DEPOSIT = 10000000
MINIMUM_GUARANTEE = 1000000

class Instrument(sp.Contract):
    def __init__(self, schedule, duration, interval, periods, start):
        self.init(
            schedule = schedule,
            duration = duration,
            interval = interval,
            periods = periods,
            start = start,
            freeCollateral = sp.mutez(0),
            balances = sp.big_map(
                tkey = sp.TAddress,
                tvalue = sp.TRecord(
                    balance = sp.TNat,
                    approvals = sp.TMap(k = sp.TAddress, v = sp.TNat),
                )
            ),
            collateral = sp.big_map(tkey = sp.TAddress, tvalue = sp.TNat),
            guarantors = sp.list([], t = sp.TAddress)
        )

    @sp.entry_point
    def default(self):
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
            wholeCoins = sp.fst(coins.open_some())
            sp.verify(tokenBalance.value > wholeCoins, message = "Deposit too low")
            requiredCollateral.value = sp.utils.nat_to_tez(sp.as_nat(tokenBalance.value - wholeCoins))
        sp.trace('requiredCollateral')
        sp.trace(requiredCollateral.value)
        sp.verify(requiredCollateral.value <= self.data.freeCollateral, message = "Insufficient collateral")

        self.data.freeCollateral -= requiredCollateral.value

        sp.if ~ self.data.balances.contains(sp.sender):
            self.data.balances[sp.sender] = sp.record(balance = tokenBalance.value, approvals = {})
        sp.else:
            self.data.balances[sp.sender].balance += tokenBalance.value

    @sp.entry_point
    def redeem(self, amount):
        sp.set_type(amount, sp.TNat)

        sp.verify(self.data.balances.contains(sp.sender), message = "Address has no balance")
        # TODO: allow approved to redeem
        sp.verify(self.data.balances[sp.sender].balance >= amount, message = "Insufficient token balance")

        currentPeriod = sp.local('currentPeriod', self.getPeriod())

        xtzBalance = sp.split_tokens(self.data.schedule[currentPeriod.value], amount, 1)

        releasedCollateral = sp.split_tokens(sp.tez(1) - self.data.schedule[currentPeriod.value], amount, 1)

        self.data.freeCollateral += releasedCollateral

        remainingBalance = sp.as_nat(self.data.balances[sp.sender].balance - amount)
        sp.if (remainingBalance > 0):
            self.data.balances[sp.sender].balance = remainingBalance
        sp.else:
            del self.data.balances[sp.sender]

        sp.send(sp.sender, xtzBalance)

    @sp.entry_point
    def transfer(self, params):
        sp.set_type(params.source, sp.TAddress)
        sp.set_type(params.destination, sp.TAddress)
        sp.set_type(params.tokenBalance, sp.TNat)

        sp.verify(sp.sender == params.destination , message = "Invalid source")
        sp.verify(self.data.balances.contains(params.source), message = "Address has no balance")
        sp.verify(params.source != params.destination, message = "Invalid destination")
        # TODO: check owner balance, not just approver
        sp.verify(self.data.balances[params.source].approvals[params.destination] >= params.tokenBalance, message = "Insufficient token balance")

        sp.if ~ self.data.balances.contains(params.destination):
            self.data.balances[params.destination] = sp.record(balance = params.tokenBalance, approvals = {})
        sp.else:
            self.data.balances[params.destination].balance += params.tokenBalance

        self.data.balances[params.source].balance = sp.as_nat(self.data.balances[params.source].balance - params.tokenBalance)
        self.data.balances[params.source].approvals[params.destination] = sp.as_nat(self.data.balances[params.source].approvals[params.destination] - params.tokenBalance)

    @sp.entry_point
    def approve(self, spender, amount):
        sp.set_type(spender, sp.TAddress)
        sp.set_type(amount, sp.TNat)

        sp.verify(self.data.balances.contains(sp.sender), message = "Address has no balance")
        sp.verify(sp.sender != spender, message = "Invalid spender")
        sp.verify(self.data.balances[sp.sender].balance >= amount, message = "Insufficient token balance")
        sp.verify((self.data.balances[sp.sender].approvals.get(spender, default_value = sp.nat(0)) == 0) | (amount == 0), "Unsafe allowance change")

        self.data.balances[sp.sender].approvals[spender] = amount

    ## views
    # redeemable value for holder
    # redeemable value for guarantor
    # @sp.onchain_view
    # schedule = schedule,
    # duration = duration,
    # interval = interval,
    # periods = periods,
    # start = start,
    # freeCollateral = sp.mutez(0),
    # balances = sp.big_map(
    #     tkey = sp.TAddress,
    #     tvalue = sp.TRecord(
    #         balance = sp.TNat,
    #         approvals = sp.TMap(k = sp.TAddress, v = sp.TNat),
    #     )
    # )

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

        sp.for depositor in depositors:
            sp.if (self.data.balances.contains(depositor)):
                xtzBalance = sp.split_tokens(self.data.schedule[currentPeriod.value], self.data.balances[depositor].balance, 1)
                releasedCollateral = sp.split_tokens(sp.tez(1) - self.data.schedule[currentPeriod.value], self.data.balances[depositor].balance, 1)

                self.data.freeCollateral += releasedCollateral

                self.data.balances[depositor].balance = sp.nat(0)
                self.data.balances[depositor].approvals = sp.map()
                sp.send(depositor, xtzBalance)
            sp.else:
                pass

        sp.for depositor in depositors:
            del self.data.balances[depositor]

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
        sp.if (self.data.freeCollateral > currentGuarantorBalance):
            sp.result(currentGuarantorBalance)
        sp.else:
            sp.result(self.data.freeCollateral)

    @sp.onchain_view(pure=True)
    def getDepositorRedeemableValue(self, depositor):
        sp.set_type(depositor, sp.TAddress)

        sp.verify(self.data.balances.contains(depositor), message = "Address has no balance")

        currentPeriod = sp.local('currentPeriod', self.getPeriod())

        sp.result(sp.split_tokens(self.data.schedule[currentPeriod.value], self.data.balances[depositor].balance, 1))

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

        newCollateralBalance = sp.utils.mutez_to_nat(sp.balance) # balance has already increased by sp.amount (xtz value of operation)
        currentCollateralBalance = sp.utils.nat_to_mutez(sp.as_nat(sp.utils.mutez_to_nat(sp.balance) - increase))

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
        sp.set_type(decrease, sp.TNat)

        currentCollateralBalance = sp.balance
        newCollateralBalance = sp.as_nat(sp.utils.mutez_to_nat(sp.balance) - decrease)

        removeGuarantor = sp.local('removeGuarantor', False)
        sp.for guarantor in self.data.guarantors:
            currentGuarantorBalance = sp.split_tokens(currentCollateralBalance, self.data.collateral[guarantor], sp.nat(1000000))

            sp.if (guarantor != sp.sender):
                newGuarantorShare = sp.utils.mutez_to_nat(currentGuarantorBalance) * sp.nat(1000000) / newCollateralBalance
                self.data.collateral[guarantor] = newGuarantorShare
            sp.else:
                newGuarantorBalance = sp.local('newGuarantorBalance', sp.as_nat(sp.utils.mutez_to_nat(currentGuarantorBalance) - decrease))

                sp.if (newGuarantorBalance.value < sp.nat(20)):
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

@sp.add_test("Instrument")
def test():
    scenario = sp.test_scenario()

    scenario.h1("Trustless Staking Token Tests")
    scenario.table_of_contents()

    alice = sp.test_account("Alice") # guarantor
    bob = sp.test_account("Robert") # guarantor
    cindy = sp.test_account("Cindy") # attacker
    david = sp.test_account("David") # depositor
    elanore = sp.test_account("Elanore") # depositor
    francois = sp.test_account("Francois") # baker/validator
    gwen = sp.test_account("Gwendolyn") # depositor

    rates = [952380, 957557, 962763, 967996, 973258, 978548, 983868, 989216, 994593, 1000000, 1000000] # TODO: adding n+1th item is a bug
    schedule = { i : sp.mutez(rates[i]) for i in range(0, len(rates) ) }
    duration = sp.nat(60*60*24*10)
    interval = sp.nat(60*60*24)
    periods = 10
    start = sp.timestamp(1000)

    scenario.h2("Accounts")
    scenario.show([alice, bob, cindy, david, elanore])

    scenario.h2("Contract")
    instrument = Instrument(schedule, duration, interval, periods, start)
    scenario += instrument

    scenario.h2("Period 0")
    time = sp.timestamp(60*60*24*0 + 1001)

    scenario.h3("Cindy fails to deposit 1000xtz")
    scenario += instrument.deposit().run(sender = cindy, amount = sp.tez(1000), now = time, valid = False)

    scenario.h3("Alice increases collateral by 1000xtz")
    scenario += instrument.depositCollateral().run(sender = alice, amount = sp.tez(1000), now = time)

    scenario.h3("Robert increases collateral by 1000xtz")
    scenario += instrument.depositCollateral().run(sender = bob, amount = sp.tez(1000), now = time)

    scenario.h3("Cindy fails to deposit 50,000 xtz")
    scenario += instrument.deposit().run(sender = cindy, amount = sp.tez(50000), now = time, valid = False)

    scenario.h3("Gwendolyn deposits 1000xtz")
    scenario += instrument.deposit().run(sender = gwen, amount = sp.tez(1000), now = time)

    scenario.h2("Period 1")
    time = sp.timestamp(60*60*24*1 + 1001)

    scenario.h3("Francois deposits 100xtz reward")
    scenario += instrument.default().run(sender = francois, amount = sp.tez(100), now = time)

    scenario.h3("Cindy fails to redeem 100 tokens")
    scenario += instrument.redeem(sp.nat(100)).run(sender = cindy, now = time, valid = False)

    scenario.h3("David deposits 1000xtz")
    scenario += instrument.deposit().run(sender = david, amount = sp.tez(1000), now = time)

    scenario.h2("Period 2")
    time = sp.timestamp(60*60*24*2 + 1001)

    scenario.h3("Francois deposits 100xtz reward")
    scenario += instrument.default().run(sender = francois, amount = sp.tez(100), now = time)

    scenario.h3("David approves an allowance of 500 tokens for Elanore")
    scenario += instrument.approve(spender = elanore.address, amount = 500).run(sender = david, now = time)

    scenario.h3("David deposits 1000xtz for a token balance of xxx")    
    scenario += instrument.deposit().run(sender = david, amount = sp.tez(1000), now = time)

    scenario.h2("Period 3")
    time = sp.timestamp(60*60*24*3 + 1001)

    scenario.h3("Francois deposits 100xtz reward")
    scenario += instrument.default().run(sender = francois, amount = sp.tez(100), now = time)

    scenario.h3("Elanore pulls 400 tokens from David's allowance")
    scenario += instrument.transfer(destination = elanore.address, source = david.address, tokenBalance = 400).run(sender = elanore, now = time)

    # scenario.h3("David redeems 1050 tokens for xxx xtz")
    # scenario += instrument.redeem(sp.nat(1050)).run(sender = david, now = time)

    scenario.h2("Period 4")
    time = sp.timestamp(60*60*24*4 + 1001)

    scenario.h3("Francois deposits 100xtz reward")
    scenario += instrument.default().run(sender = francois, amount = sp.tez(100), now = time)

    scenario.h3("Alice changes the delegate")
    scenario += instrument.setDelegate(sp.some(francois.public_key_hash)).run(sender = alice, now = time)

    #scenario += instrument.redeem(amount = sp.nat(1050)).run(sender = bob, now = 60*60*24*8 + 1)
    #scenario += instrument.send(destination = cindy.address, tokenBalance = sp.mutez(1_000_000_000)).run(sender = bob, now = 60*60*24*3)
    #scenario += instrument.redeem(amount = sp.nat(1000)).run(sender = cindy, now = 60*60*24*8 + 1)
    #scenario += instrument.default().run(sender = payer, amount = sp.mutez(500_000_000))
    #scenario += instrument.setDelegate(baker = sp.some(david.public_key_hash)).run(sender = issuer)
    #scenario += instrument.withdrawCollateral(amount = sp.mutez(1_450_000_000)).run(sender = issuer, now = 60*60*24*8 + 1, valid = False)

    scenario.h2("Period 5 - 8")
    scenario.h3("Francois deposits 100xtz reward")
    scenario += instrument.default().run(sender = francois, amount = sp.tez(100), now = time)

    scenario.h3("Francois deposits 100xtz reward")
    scenario += instrument.default().run(sender = francois, amount = sp.tez(100), now = time)

    scenario.h3("Francois deposits 100xtz reward")
    scenario += instrument.default().run(sender = francois, amount = sp.tez(100), now = time)

    scenario.h3("Francois deposits 100xtz reward")
    scenario += instrument.default().run(sender = francois, amount = sp.tez(100), now = time)

    scenario.h2("Period 9")
    time = sp.timestamp(60*60*24*9 + 1001)

    scenario.h3("Alice fails to terminate contract")
    scenario += instrument.terminate([david.address, elanore.address]).run(sender = alice, now = time, valid = False)

    scenario.h3("Cindy fails to terminate contract")
    scenario += instrument.terminate([david.address, elanore.address]).run(sender = cindy, now = time, valid = False)

    scenario.h3("Francois deposits 100xtz reward")
    scenario += instrument.default().run(sender = francois, amount = sp.tez(100), now = time)

    scenario.h3("Francois deposits 100xtz reward")
    scenario += instrument.default().run(sender = francois, amount = sp.tez(100), now = time)

    scenario.h2("Period 11")
    time = sp.timestamp(60*60*24*11 + 1001)

    scenario.h3("Cindy fails to terminate contract")
    scenario += instrument.terminate([david.address, elanore.address]).run(sender = cindy, now = time, valid = False)

    scenario.h3("Francois deposits 100xtz reward")
    scenario += instrument.default().run(sender = francois, amount = sp.tez(100), now = time)

    scenario.h3("Cindy fails to withdraw collateral")
    scenario += instrument.withdrawCollateral(sp.nat(1000000)).run(sender = cindy, now = time, valid = False)

    scenario.h3("Alice withdraws the free collateral")
    scenario += instrument.withdrawCollateral(sp.nat(100000000)).run(sender = alice, now = time)

    scenario.h3("Withdraw Alice's remaining deposit amount")
    scenario.show(sp.view("getGuarantorRedeemableValue", instrument.address, alice.address, t = sp.TMutez))
    scenario += instrument.withdrawCollateral(sp.nat(100000000)).run(sender = alice, now = time)

    scenario.h3("Depositors withdraw their tokens")
    scenario += instrument.redeem(sp.nat(521)).run(sender = david, now = time)
    scenario += instrument.redeem(sp.nat(300)).run(sender = elanore, now = time)

    scenario.h2("Period 15")
    time = sp.timestamp(60*60*24*15 + 1001)
    # scenario.h3("Withdraw Robert's deposit amount")
    # scenario.show(sp.view("getGuarantorRedeemableValue", instrument.address, bob.address, t = sp.TMutez))
    # scenario += instrument.withdrawCollateral(sp.nat(1502209334)).run(sender = bob, now = time)

    # scenario.h3("Withdraw Alice's remaining deposit amount")
    # scenario.show(sp.view("getGuarantorRedeemableValue", instrument.address, alice.address, t = sp.TMutez))
    # scenario += instrument.withdrawCollateral(sp.nat(1354862991)).run(sender = alice, now = time)

    scenario.show(instrument.balance)
    scenario.verify(instrument.balance < sp.mutez(100000))

    scenario.h3("Alice terminates contract")
    scenario += instrument.terminate([david.address, elanore.address]).run(sender = alice, now = time)

    #scenario.simulation(instrument)
