# Reference implementation of the Trustless Staking Token for Tezos
# Written using SmartPy (https://smartpy.io/ide)
# Mike Radin
# 2022, May; version 2.6

import smartpy as sp

BalanceTransferType = sp.TRecord(from_ = sp.TAddress, to_ = sp.TAddress, value = sp.TNat).layout(("from_ as from", ("to_ as to", "value")))
BalanceMintType = sp.TRecord(destination = sp.TAddress, amount = sp.TNat).layout(("destination", "amount"))
BalanceBurnType = sp.TRecord(source = sp.TAddress, amount = sp.TNat).layout(("source", "amount"))
TransferHookType = sp.TRecord(source = sp.TAddress, amount = sp.TAddress).layout(("source", "destination")) # TODO: maybe later

VOTE_THRESHOLD = 51
VOTE_MARGIN = 2
PROPOSAL_VOTE_DURATION = 8192
PROPOSAL_APPLICATION_DURATION = 512

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
            proposal = sp.record(
                level = sp.nat(0),
                validator = sp.key_hash("tz1Ke2h7sDdakHJQh8WX4Z372du1KChsksyU"),
                votes = sp.map(l = {}, tkey = sp.TAddress, tvalue = sp.TRecord(weight = sp.TNat, vote = sp.TBool)),
                duration = sp.nat(0)
            )
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

    @sp.entry_point
    def proposeDelegate(self, delegate):
        sp.set_type(delegate, sp.TKeyHash)

        proposerBalance = sp.local('proposerBalance', sp.nat(0))
        proposerBalance.value = sp.view("getBalance", self.data.share_token, sp.sender).open_some("Incompatible view")
        sp.verify(proposerBalance.value > 0, message = "Not a guarantor")

        sp.if (sp.level < self.data.proposal.level + self.data.proposal.duration + PROPOSAL_APPLICATION_DURATION):
            sp.failwith("Proposal active")
        sp.else:
            pass

        totalSupply = sp.local('totalSupply', sp.nat(0))
        totalSupply.value = sp.view("getTotalSupply", self.data.share_token, sp.unit).open_some("Incompatible view")

        sp.if (totalSupply.value == proposerBalance.value):
            sp.set_delegate(sp.some(delegate))
        sp.else:
            proposerShare = sp.fst(sp.ediv(proposerBalance.value * sp.nat(100), totalSupply.value).open_some())

            sp.if (proposerShare >= VOTE_THRESHOLD):
                sp.set_delegate(sp.some(delegate))
            sp.else:
                self.data.proposal = sp.record(
                    level = sp.level,
                    validator = delegate,
                    votes = sp.map(tkey = sp.TAddress, tvalue = sp.TRecord(weight = sp.TNat, vote = sp.TBool)),
                    duration = sp.nat(PROPOSAL_VOTE_DURATION))
                self.data.proposal.votes[sp.sender] = sp.record(weight = proposerBalance.value, vote = True)

    @sp.entry_point
    def applyProposal(self, vote):
        sp.set_type(vote, sp.TBool)

        proposerBalance = sp.local('proposerBalance', sp.nat(0))
        proposerBalance.value = sp.view("getBalance", self.data.share_token, sp.sender).open_some("Incompatible view")
        sp.verify(proposerBalance.value > 0, message = "Not a guarantor")

        sp.verify(self.data.proposal.level != sp.nat(0), message = "No proposal")

        sp.if (sp.as_nat(sp.level - self.data.proposal.level) < self.data.proposal.duration):
            self.data.proposal.votes[sp.sender] = sp.record(weight = proposerBalance.value, vote = vote)
        sp.else:
            yeaShare = sp.local('yeaShare', sp.nat(0))
            nayShare = sp.local('nayShare', sp.nat(0))
            totalSupply = sp.local('totalSupply', sp.nat(0))
            totalSupply.value = sp.view("getTotalSupply", self.data.share_token, sp.unit).open_some("Incompatible view")

            sp.for guarantor in self.data.proposal.votes.keys():
                proposerBalance.value = sp.view("getBalance", self.data.share_token, guarantor).open_some("Incompatible view")
                proposerBalance.value += self.data.proposal.votes[guarantor].weight
                proposerBalance.value /= 2

                sp.if (self.data.proposal.votes[guarantor].vote):
                    yeaShare.value += proposerBalance.value
                sp.else:
                    nayShare.value += proposerBalance.value

            voteDifference = sp.as_nat(yeaShare.value - nayShare.value)
            voteDifferenceShare = sp.fst(sp.ediv(voteDifference * sp.nat(100), totalSupply.value).open_some())
            totalVotes = yeaShare.value + nayShare.value
            voteShare = sp.fst(sp.ediv(totalVotes * sp.nat(100), totalSupply.value).open_some())
            sp.if (voteShare > VOTE_THRESHOLD) & (voteDifferenceShare >= VOTE_MARGIN):
                sp.set_delegate(sp.some(self.data.proposal.validator))
            sp.else:
                pass

            self.data.proposal = sp.record(
                level = sp.nat(0),
                validator = sp.key_hash("tz1Ke2h7sDdakHJQh8WX4Z372du1KChsksyU"),
                votes = sp.map(l = {}, tkey = sp.TAddress, tvalue = sp.TRecord(weight = sp.TNat, vote = sp.TBool)),
                duration = sp.nat(0))

    @sp.entry_point
    def terminate(self, depositors):
        sp.set_type(depositors, sp.TList(sp.TAddress))

        guarantorBalance = sp.local('guarantorBalance', sp.nat(0))
        guarantorBalance.value = sp.view("getBalance", self.data.share_token, sp.sender).open_some("Incompatible view")
        sp.verify(guarantorBalance.value > 0, message = "Not a guarantor")

        currentPeriod = sp.local('currentPeriod', self.getPeriod())
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

        sp.if (totalShares.value == 0):
            shareIssue.value = sp.utils.mutez_to_nat(sp.amount)
        sp.else:
            sp.if (totalShares.value > 0):
                numerator = sp.local('numerator', sp.nat(0))
                numerator.value = sp.utils.mutez_to_nat(self.data.depositedCollateral + sp.amount)
                numerator.value = numerator.value * totalShares.value

                shareIssue.value = sp.as_nat(sp.fst(sp.ediv(numerator.value, sp.utils.mutez_to_nat(self.data.depositedCollateral)).open_some()) - totalShares.value)
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

        sp.send(sp.sender, sp.utils.nat_to_mutez(amount))

        # TODO: deal with dust

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
