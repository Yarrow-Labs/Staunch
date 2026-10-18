# Source

Puzzles revealed in real Chia mainnet spends, read from a full node with
`chia rpc full_node` (`get_block_spends`, `get_puzzle_and_solution`). Public
chain data.

| File | Spent at height |
|---|---|
| `cat_std.json` | 9445764 |
| `singleton.json` | 9445768 |
| `std.json` | 9445768 |
| `nft.json` | 9440049 |
| `plot_nft.json` | 9440056 |
| `warp_portal.json` | 6716314 |
| `warp_message_coin.json` | 6716314 |
| `warp_burn.json` | 9333881 |

`cat_std`: a CAT2 coin held by a standard wallet. `singleton`: a singleton
v1_1 coin. `std`: a plain standard-wallet coin. `nft`: an NFT (singleton,
state layer, ownership layer, royalty program). `plot_nft`: a plot NFT, inside
the older singleton. `warp_portal`, `warp_message_coin`, `warp_burn`:
warp.green's portal singleton, a message coin, and a wrapped CAT being burned
to bridge out.
