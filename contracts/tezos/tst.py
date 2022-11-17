# Reference implementation of the Trustless Staking Token for Tezos
# Written using SmartPy (https://smartpy.io/ide)
# Mike Radin
# 2022, April; version 2.0

import smartpy as sp

class Instrument(sp.Contract):
    def __init__(self, schedule, duration, interval, periods, issuer, start):
        self.init(
            schedule = schedule,
            duration = duration,
            interval = interval,
            periods = periods,
            issuer = issuer,
            start = start,
            freeCollateral = sp.mutez(0), # TODO: make sp.TNat
            balances = sp.big_map(
                tkey = sp.TAddress,
                tvalue = sp.TRecord(
                    balance = sp.TNat,
                    approvals = sp.TMap(k = sp.TAddress, v = sp.TNat),
                )
            )
        )

    @sp.entry_point
    def default(self):
        self.data.freeCollateral += sp.amount

    @sp.entry_point
    def deposit(self):
        sp.verify(sp.amount > sp.mutez(0), message = "Deposit too low")
        sp.verify(sp.sender != self.data.issuer, message = "Invalid address")
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

        xtzBalance = self.getRedemptionValue(amount)
        releasedCollateral = sp.utils.nat_to_tez(amount) - xtzBalance

        self.data.freeCollateral += releasedCollateral

        self.data.balances[sp.sender].balance = sp.as_nat(self.data.balances[sp.sender].balance - amount)
        sp.send(sp.sender, xtzBalance)

    @sp.entry_point
    def transfer(self, params):
        sp.set_type(params.source, sp.TAddress)
        sp.set_type(params.destination, sp.TAddress)
        sp.set_type(params.tokenBalance, sp.TNat)

        sp.verify(sp.sender == params.destination , message = "Invalid source")
        sp.verify(self.data.balances.contains(params.source), message = "Address has no balance")
        sp.verify(params.source != params.destination, message = "Invalid destination")
        #TODO: check owner balance, not just approver
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
    # @sp.onchain_view
    # schedule = schedule,
    # duration = duration,
    # interval = interval,
    # periods = periods,
    # issuer = issuer,
    # start = start,
    # freeCollateral = sp.mutez(0),
    # balances = sp.big_map(
    #     tkey = sp.TAddress,
    #     tvalue = sp.TRecord(
    #         balance = sp.TNat,
    #         approvals = sp.TMap(k = sp.TAddress, v = sp.TNat),
    #     )
    # )

    @sp.entry_point
    def setDelegate(self, delegate):
        sp.set_type(delegate, sp.TOption(sp.TKeyHash))

        sp.verify(sp.sender == self.data.issuer, message = "Privileged operation")

        sp.set_delegate(delegate)

    @sp.entry_point
    def withdrawCollateral(self, params):
        sp.verify(sp.sender == self.data.issuer, message = "Privileged operation")
        sp.verify(params.amount <= self.data.freeCollateral, message = "Insufficient free collateral")

        self.data.freeCollateral -= params.amount
        sp.send(sp.sender, params.amount)

    @sp.entry_point
    def terminate(self):
        sp.verify(sp.sender == self.data.issuer, message = "Privileged operation")

        pass

    def getPeriod(self):
        y = sp.local('y', self.data.periods)
        sp.if sp.now > self.data.start.add_seconds(sp.to_int(self.data.duration)):
            y.value = self.data.periods
        sp.else:
            ttm = sp.as_nat(self.data.duration - sp.as_nat(sp.now - self.data.start))
            y.value = (sp.as_nat(self.data.periods) - (ttm // self.data.interval))
        return y.value

    def getRedemptionValue(self, amount):
        sp.set_type(amount, sp.TNat)

        period = self.getPeriod() # TODO: needs a concept of minimum holding period

        return sp.split_tokens(self.data.schedule[period], amount, 1)

@sp.add_test("Instrument")
def test():
    scenario = sp.test_scenario()

    scenario.h1("Trustless Staking Token Tests")
    scenario.table_of_contents()

    alice = sp.test_account("Alice")
    bob = sp.test_account("Robert")
    cindy = sp.test_account("Cindy")
    david = sp.test_account("David")

    rates = [952380, 957557, 962763, 967996, 973258, 978548, 983868, 989216, 994593, 1000000]
    schedule = { i : sp.mutez(rates[i]) for i in range(0, len(rates) ) }
    duration = sp.nat(60*60*24*10)
    interval = sp.nat(60*60*24)
    periods = 10
    issuer = sp.test_account("Issuer")
    start = sp.timestamp(1000)

    scenario.h2("Accounts")
    scenario.show([alice, bob, cindy, david])

    scenario.h2("Contract")
    instrument = Instrument(schedule, duration, interval, periods, issuer.address, start)
    scenario += instrument

    scenario.h2("Period 0")
    time = sp.timestamp(60*60*24*0 + 1001)
    scenario.h3("Alice fails to deposit 1000xtz")
    scenario += instrument.deposit().run(sender = alice, amount = sp.tez(1000), now = time, valid = False)

    scenario.h3("Issuer increases collateral by 1000xtz")
    scenario += instrument.default().run(sender = issuer, amount = sp.tez(1000), now = time)

    scenario.h3("Robert fails to deposit 40,000 xtz")
    scenario += instrument.deposit().run(sender = bob, amount = sp.tez(40000), now = time, valid = False)

    scenario.h3("Robert deposits 1,000xtz for a token balance of 1044")
    scenario += instrument.deposit().run(sender = bob, amount = sp.tez(1000), now = time)

    scenario.h2("Period 1")
    time = sp.timestamp(60*60*24*1 + 1001)

    scenario.h3("Cindy fails to redeem 100 tokens")
    scenario += instrument.redeem(sp.nat(100)).run(sender = cindy, now = time, valid = False)

    scenario.h2("Period 2")
    time = sp.timestamp(60*60*24*2 + 1001)

    scenario.h3("Robert approves an allowance of 500 tokens for David")
    scenario += instrument.approve(spender = david.address, amount = 500).run(sender = bob, now = time)

    scenario.h3("Robert deposits 1000xtz for a token balance of xxx")    
    scenario += instrument.deposit().run(sender = bob, amount = sp.tez(1000), now = time)

    scenario.h2("Period 3")
    time = sp.timestamp(60*60*24*3 + 1001)

    scenario.h3("David pulls 400 tokens from Robert's allowance")
    scenario += instrument.transfer(destination = david.address, source = bob.address, tokenBalance = 400).run(sender = david, now = time)

    scenario.h3("Robert redeems 1050 tokens for xxx xtz")
    scenario += instrument.redeem(sp.nat(1050)).run(sender = bob, now = time)

    scenario.h2("Period 4")
    time = sp.timestamp(60*60*24*4 + 1001)

    scenario.h3("Issuer changes the delegate")
    scenario += instrument.setDelegate(sp.some(david.public_key_hash)).run(sender = issuer, now = time)

    #scenario += instrument.redeem(amount = sp.nat(1050)).run(sender = bob, now = 60*60*24*8 + 1)
    #scenario += instrument.send(destination = cindy.address, tokenBalance = sp.mutez(1_000_000_000)).run(sender = bob, now = 60*60*24*3)
    #scenario += instrument.redeem(amount = sp.nat(1000)).run(sender = cindy, now = 60*60*24*8 + 1)
    #scenario += instrument.default().run(sender = payer, amount = sp.mutez(500_000_000))
    #scenario += instrument.setDelegate(baker = sp.some(david.public_key_hash)).run(sender = issuer)
    #scenario += instrument.withdrawCollateral(amount = sp.mutez(1_450_000_000)).run(sender = issuer, now = 60*60*24*8 + 1, valid = False)

    scenario.h2("Period 11")
    time = sp.timestamp(60*60*24*11 + 1001)

    scenario.p("Cindy fails to withdraw collateral")
    scenario += instrument.withdrawCollateral(amount = sp.tez(1)).run(sender = cindy, valid = False)

    scenario.p("Issuer withdraws the free collateral")
    scenario += instrument.withdrawCollateral(amount = sp.tez(907)).run(sender = issuer)

    #scenario.simulation(instrument)
    
