require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config({ path: "../.env" });

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: "0.8.20",
  networks: {
    base: {
      url: process.env.BASE_RPC_URL || "https://mainnet.base.org",
      accounts: process.env.TREASURY_PRIVATE_KEY && process.env.TREASURY_PRIVATE_KEY.startsWith('0x') 
        ? [process.env.TREASURY_PRIVATE_KEY] 
        : [],
      chainId: 8453,
    },
    baseSepolia: {
      url: process.env.BASE_TESTNET_RPC_URL || "https://sepolia.base.org",
      accounts: process.env.TREASURY_PRIVATE_KEY && process.env.TREASURY_PRIVATE_KEY.startsWith('0x')
        ? [process.env.TREASURY_PRIVATE_KEY]
        : [],
      chainId: 84532,
    },
  },
  etherscan: {
    apiKey: {
      base: process.env.BASESCAN_API_KEY || "",
    },
  },
};
