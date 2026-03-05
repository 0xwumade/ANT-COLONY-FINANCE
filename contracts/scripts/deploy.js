const hre = require("hardhat");

async function main() {
  console.log("🐜 Deploying Ant Colony Finance contract to Base...");

  const [deployer] = await hre.ethers.getSigners();
  console.log(`Deploying from: ${deployer.address}`);

  // Constructor parameters
  const operator = deployer.address;  // Colony operator (Python backend)
  const threshold = 6500;             // 65% consensus threshold
  const swarmSize = 100;              // Number of agents

  const AntColonyFinance = await hre.ethers.getContractFactory("AntColonyFinance");
  const colony = await AntColonyFinance.deploy(operator, threshold, swarmSize);

  await colony.waitForDeployment();

  const address = await colony.getAddress();
  console.log(`✅ AntColonyFinance deployed to: ${address}`);
  console.log(`\nAdd this to your .env file:`);
  console.log(`COLONY_CONTRACT_ADDRESS=${address}`);
  console.log(`\nTo verify on Basescan, run:`);
  console.log(`npx hardhat verify --network ${hre.network.name} ${address} ${operator} ${threshold} ${swarmSize}`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
