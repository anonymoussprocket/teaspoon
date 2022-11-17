# Teaspoon: a Trustless Staking Platform

Teaspoon, tsp, Trustless Staking Platform, is a collection of smart contracts allowing some participants to collect guaranteed returns of some amount from guarantors who take on the risk of providing this guarantee while receiving somewhat larger rewards for that risk.

## Theory of Operation

There are three types of participants in this platform. The guarantors, the depositors and the platform validators. The guaranteed return for depositors is provided by the guarantors who in turn collect the rewards provided by the platform validators as part of the Proof-of-Stake consensus mechanism on the relevant chain.

At the moment, tsp is available on Tezos, active work is being done to deploy a similar product to Ethereum. We're also exploring other chains.

Guarantors get tokens when they deposit into the contract. These tokens are fully transferrable. Meaning it would be possible to deploy an AMM pool, provide liquidity and swap these tokens in order to exit a position early.

The number of tokens issues to a guarantor depends on the current guarantor balance in the contract and how much the contract has already received in rewards from the validator.

The contracts cannot function without some balance of guarantee. For example, if a guarantor deposits 1,000 coins and the contract is configured for 1 year period paying out 5% annualized returns, then the contract will accept up to 20,000 coins from depositors because that is most it can guarantee a 5% return for.

Similarly, for their deposits, depositors also get fully transferrable tokens. These are different from guarantor tokens, but they behave the same way, that is they could potentially be swapped on an AMM, sent between accounts, etc.

The number of tokens issued to depositors depends on the balance they send and the current interest accrual period.

Interest for depositors is accrued in periods on this platform. All this information is available in the contract storage for those who'd like to explore it. Depositor interest is paid on redemption. To redeem tokens, depositors send them back to the contract to be burned and exchanged for the native coin of the chain, for Tezos it's XTZ. To collect the full interest the depositor should deposit at the start of the period and withdraw after it ends. For example if the contract is offering 5% annualized guaranteed return over 6 months with weekly accrual. That means the depositor should enter right at the start of the six months and redeem just after the end of the six months. The contract only provides interest on fully completed accrual periods. Redeeming in the middle of the current period will only pay out the interest through the latest full period.

## Using the Platform

As always with DeFi, it's important to understand how the platform works in order to use it successfully.

### As a Depositor

Depositors remove the risk on delegation rewards by contributing their coins into the platform. The contract is written to only accept the maximum balance it can guarantee returns on. To get the maximum returns, depositors should deposit close to the start of the validity period and withdraw just after the end of it.

### As a Guarantor

Guarantors are able to leverage their coin holdings by guaranteeing a return to depositors thereby making larger than normal returns on their capital. Depositing guarantees is more beneficial towards the start of the validity period rather than towards the end.

To get the maximum amount of returns, guarantors should redeem their tokens after all of the depositors have withdrawn their deposits. Guarantors can also terminate the contract by redeeming all the depositors after the end of the validity period.

### As a Validator

The contract makes returns for guarantors by distributing proportional delegation rewards from the validator to the token holders. Guarantors control the validator that the contract balance is delegated to.

## Risks

### Risks for Guarantors

- Smart contract risk. There is some chance the contract has unforeseen bugs which may lead to unexpectedly low returns or loss of funds. These contracts are fully autonomous and do not offer any recovery functionality.
- A malicious guarantor can delegate the contract to a private baker who will never pay delegation rewards into the contract. This would be the equivalent of losing funds if the platform is fully subscribed by depositors.
- Counter-party risk a well-meaning guarantor may unintentionally delegate the contract to a validator who simply refuses to pay delegation rewards.
- Early withdrawal leads to lower than expected rewards. Withdrawal burns guarantor tokens.

### Risks for Depositors

- Just like guarantors, depositors who use this platform accept that it may not function as intended and result in a loss of funds.

## Releases

### v1

Initial concept was developed between Nov 2019 and February 2020. It was released publicly at that time. The original version was lacking decentralization, depositor and guarantor token transferability among other things.

### v2

Work started on a decentralized version in March 2022. Several iterations were made with the functionality evolving as follows.

- 2.0: Contract updates for new Tezos blockchain features.
- 2.1: Decentralized guarantee deposits.
- 2.2: Decentralized delegate setting.
- 2.3: External depositor token.
- 2.4: External guarantor token.
- 2.5: Improved collateral tracking.
- 2.6: Proposal-based delegate setting.

### v3

- Yes.

### Roadmap

This mechanism would work on other proof-of-stake chains with caveats for stake liquidity. For example the same exact mechanics would not apply on Ethereum, even now with *The Merge* due to stake being locked for an undermined duration. Liquid markets for staked tokens (Lido/stETH) can be used as a stand-in.

Another version of the platform will be made available that allows the interest to be paid in tokens instead of coins. Meaning guarantors will fund a guarantee with a token like kUSD on Tezos or USDC on Ethereum, depositors will deposit the blockchain coin but get interest in some token while guarantors will collect rewards from delegation payments denominated in coins.

A DAO may be launched to manage the project.

## Implementation details

### Tezos

#### Interesting entrypoints

- `getGuarantorRedeemableValue address` Returns the current value of the guarantor tokens held by a given address. This value is based on currently-free collateral, not necessarily the final value at the end of the period.
- `getGuaranteeRedeemableValue nat` Returns the current value of the given guarantor token balance.
- `getDepositorRedeemableValue address` Returns the current value, including interest, of depositor tokens held by a given address.
- `getDepositRedeemableValue nat` Returns the current value, including interest, of the given depositor token balance.
- `terminate` A function that guarantor token holders can execute **after** the validity period is over to push the depositor balances back to their accounts. This operation frees up all the available collateral and allows guarantors to withdraw the maximum value.

### Source Code

Blockchains are implicitly open-source therefore as soon as they're deployed, the source is available. Tezos contracts are written in SmartPy.

### Tests

[SmartPy IDE tests](https://smartpy.io/ide?cid=QmVFrUkSDXqc8kifVbVdkLzmf545vaWJr2pNE1y15m4yeW&k=d00ac3005448a2966b17)

## Known issues

- There are occasional rounding errors, they were deemed to be small enough. This may be addressed in a future release.

## A Note on Decentralization

This platform has no concept of a manager account. Once the contracts are deployed and bootstrapped they operate autonomously. These contracts are not upgradeable, funds sent to the contract unintentionally cannot be recovered. By using this platform participants understand that loss of funds may occur and there is no recourse since the contracts have no manager.

After deployment the only thing that can change is the contract balance which is controlled by deposits and withdrawal of coins from guarantors and depositors. Interest rate, accrual period duration, validity period duration cannot be changed.

## Earlier work: 

[Trustless Staking Token](https://github.com/Cryptonomic/Smart-Contracts/blob/master/RFC/trustless-staking-token.md)
