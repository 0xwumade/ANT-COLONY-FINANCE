const hre = require("hardhat");

async function main() {
  console.log("🐜 Deploying Ant Colony Finance contract to Base...");

  const AntColonyFinance = await hre.ethers.getContractFactory("AntColonyFinance");
  const colony = await AntColonyFinance.deploy();

  await colony.waitForDeployment();

  const address = await colony.getAddress();
  console.log(`✅ AntColonyFinance deployed to: ${address}`);
  console.log(`\nAdd this to your .env file:`);
  console.log(`COLONY_CONTRACT_ADDRESS=${address}`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
