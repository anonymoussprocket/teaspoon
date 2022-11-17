import smartpy as sp

class ShareToken(sp.Contract):
    def __init__(self, _deployer, _metadata,):
        self.init(
            deployer = _deployer,
            parent = _deployer,
            metadata = _metadata,
            balances = sp.big_map(
                tkey = sp.TAddress,
                tvalue = sp.TRecord(
                    balance = sp.TNat,
                    approvals = sp.TMap(k = sp.TAddress, v = sp.TNat)
                )
            ),
            total_supply = sp.nat(1000000)
        )

    @sp.entry_point
    def bootstrap(self, _parent):
        sp.set_type(_parent, sp.TAddress)

        sp.verify(sp.source == self.data.deployer, message = "Invalid request")
        sp.verify(self.data.deployer == self.data.parent, message = "Already bootstrapped")

        self.data.parent = _parent
        self.data.deployer = sp.address('tz1Ke2h7sDdakHJQh8WX4Z372du1KChsksyU')

    @sp.entry_point
    def default(self):
        pass

    @sp.entry_point
    def transfer(self, params):
        sp.set_type(
            params,
            sp.TRecord(source = sp.TAddress, destination = sp.TAddress, amount = sp.TNat)
                .layout(("source", ("destination", "amount"))))

        sp.verify(self.data.balances.contains(params.source), message = "No balance")
        sp.verify(params.source != params.destination, message = "Invalid destination")
        sp.verify(self.data.balances[params.source].balance >= params.amount, message = "Insufficient balance")
        sp.if (sp.sender != params.source):
            sp.verify(self.data.balances[params.source].approvals[sp.sender] >= params.amount, message = "Insufficient allowance")
        sp.else:
            pass

        sp.if ~ self.data.balances.contains(params.destination):
            self.data.balances[params.destination] = sp.record(balance = params.amount, approvals = {})
        sp.else:
            self.data.balances[params.destination].balance += params.amount

        self.data.balances[params.source].balance = sp.as_nat(self.data.balances[params.source].balance - params.amount)

        sp.if (sp.sender != params.source):
            self.data.balances[params.source].approvals[params.destination] = sp.as_nat(self.data.balances[params.source].approvals[params.destination] - params.amount)
        sp.else:
            pass

        RegisterShareReference = sp.contract(RegisterShareType, self.data.parent, entry_point="registerShare").open_some()
        setShare = sp.record(account = params.destination, amount = self.data.balances[params.destination].balance)
        setShare = sp.set_type_expr(setShare, RegisterShareType)
        sp.transfer(setShare, sp.tez(0), RegisterShareReference)

        RegisterShareReference = sp.contract(RegisterShareType, self.data.parent, entry_point="registerShare").open_some()
        setShare = sp.record(account = params.source, amount = self.data.balances[params.source].balance)
        setShare = sp.set_type_expr(setShare, RegisterShareType)
        sp.transfer(setShare, sp.tez(0), RegisterShareReference)

        # TODO: clean up approvals map
        # TODO: clean up balances map

    @sp.entry_point
    def approve(self, spender, amount):
        sp.set_type(spender, sp.TAddress)
        sp.set_type(amount, sp.TNat)

        sp.verify(self.data.balances.contains(sp.sender), message = "No balance")
        sp.verify(sp.sender != spender, message = "Invalid spender")
        sp.verify((self.data.balances[sp.sender].approvals.get(spender, default_value = sp.nat(0)) == 0) | (amount == 0), "Unsafe allowance change")

        sp.if (amount > 0):
            self.data.balances[sp.sender].approvals[spender] = amount
        sp.else:
            del self.data.balances[sp.sender].approvals[spender]

    @sp.onchain_view(pure=True)
    def getAllowance(self, params):
        sp.set_type(params.owner, sp.TAddress)
        sp.set_type(params.spender, sp.TAddress)

        amount = sp.local('amount', sp.nat(0))
        sp.if ~self.data.balances.contains(params.owner):
            amount.value = sp.nat(0)
        sp.else:
            sp.if ~self.data.balances[params.owner].approvals.contains(params.spender):
                amount.value = sp.nat(0)
            sp.else:
                amount.value = self.data.balances[params.owner].approvals[params.spender]

        sp.result(amount.value)

    @sp.onchain_view(pure=True)
    def getBalance(self, owner):
        sp.set_type(owner, sp.TAddress)

        amount = sp.local('amount', sp.nat(0))
        sp.if (self.data.balances.contains(owner)):
            amount.value = self.data.balances[owner].balance
        sp.else:
            amount.value = sp.nat(0)

        sp.result(amount.value)

    @sp.onchain_view(pure=True)
    def getTotalSupply(self):
        sp.result(self.data.total_supply)

    @sp.entry_point
    def setBalance(self, params):
        sp.set_type(params, sp.TRecord(account = sp.TAddress, amount = sp.TNat).layout(("account", "amount")))

        sp.verify(sp.sender == self.data.parent, message = "Privileged operation")

        sp.if (params.amount > sp.nat(0)):
            sp.if ~self.data.balances.contains(params.account):
                self.data.balances[params.account] = sp.record(balance = params.amount, approvals = {})
            sp.else:
                self.data.balances[params.account].balance = params.amount
        sp.else:
            sp.if self.data.balances.contains(params.account):
                del self.data.balances[params.account]
            sp.else:
                pass
