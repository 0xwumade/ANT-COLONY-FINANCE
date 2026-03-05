const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AntColonyFinance", function () {
  let antColony;
  let owner;
  let addr1;

  beforeEach(async function () {
    [owner, addr1] = await ethers.getSigners();
    
    const AntColonyFinance = await ethers.getContractFactory("AntColonyFinance");
    // Constructor params: operator address, threshold (6500 = 65%), swarm size (100)
    antColony = await AntColonyFinance.deploy(owner.address, 6500, 100);
    await antColony.waitForDeployment();
  });

  describe("Deployment", function () {
    it("Should deploy successfully", async function () {
      expect(await antColony.getAddress()).to.be.properAddress;
    });

    it("Should set the right owner", async function () {
      expect(await antColony.owner()).to.equal(owner.address);
    });
  });

  describe("Decision Logging", function () {
    it("Should log a BUY decision", async function () {
      const tokenAddress = "0x532f27101965dd16442E59d40670FaF5eBB142E4"; // BRETT
      const action = "BUY";
      const confidence = 7500; // 75%
      const signalCount = 100;
      const buyScore = 7500;
      const sellScore = 2500;

      await expect(
        antColony.logDecision(tokenAddress, action, confidence, signalCount, buyScore, sellScore)
      )
        .to.emit(antColony, "ColonyDecision")
        .withArgs(1, tokenAddress, action, confidence, signalCount, buyScore, sellScore, await ethers.provider.getBlock('latest').then(b => b.timestamp + 1));
    });

    it("Should log a SELL decision", async function () {
      const tokenAddress = "0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed"; // DEGEN
      const action = "SELL";
      const confidence = 8000; // 80%
      const signalCount = 120;
      const buyScore = 2000;
      const sellScore = 8000;

      await expect(
        antColony.logDecision(tokenAddress, action, confidence, signalCount, buyScore, sellScore)
      ).to.emit(antColony, "ColonyDecision");
    });

    it("Should log a HOLD decision", async function () {
      const tokenAddress = "0x532f27101965dd16442E59d40670FaF5eBB142E4";
      const action = "HOLD";
      const confidence = 5000; // 50%
      const signalCount = 80;
      const buyScore = 4500;
      const sellScore = 4500;

      await expect(
        antColony.logDecision(tokenAddress, action, confidence, signalCount, buyScore, sellScore)
      ).to.emit(antColony, "ColonyDecision");
    });

    it("Should only allow operator to log decisions", async function () {
      const tokenAddress = "0x532f27101965dd16442E59d40670FaF5eBB142E4";
      const action = "BUY";
      const confidence = 7500;
      const signalCount = 100;
      const buyScore = 7500;
      const sellScore = 2500;

      await expect(
        antColony.connect(addr1).logDecision(tokenAddress, action, confidence, signalCount, buyScore, sellScore)
      ).to.be.revertedWith("AntColony: not operator");
    });

    it("Should increment decision count", async function () {
      const tokenAddress = "0x532f27101965dd16442E59d40670FaF5eBB142E4";
      const action = "BUY";
      const confidence = 7500;
      const signalCount = 100;
      const buyScore = 7500;
      const sellScore = 2500;

      expect(await antColony.decisionCount()).to.equal(0);
      
      await antColony.logDecision(tokenAddress, action, confidence, signalCount, buyScore, sellScore);
      expect(await antColony.decisionCount()).to.equal(1);
      
      await antColony.logDecision(tokenAddress, action, confidence, signalCount, buyScore, sellScore);
      expect(await antColony.decisionCount()).to.equal(2);
    });
  });

  describe("Trade Execution Logging", function () {
    it("Should log a trade execution", async function () {
      const tokenAddress = "0x532f27101965dd16442E59d40670FaF5eBB142E4";
      const action = "BUY";
      const confidence = 7500;
      const signalCount = 100;
      const buyScore = 7500;
      const sellScore = 2500;

      // First log a decision
      await antColony.logDecision(tokenAddress, action, confidence, signalCount, buyScore, sellScore);
      
      const decisionId = 1;
      const amountWei = ethers.parseEther("0.1");
      const txHash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef";

      await expect(
        antColony.logExecution(decisionId, tokenAddress, action, amountWei, txHash)
      )
        .to.emit(antColony, "TradeExecuted")
        .withArgs(decisionId, tokenAddress, action, amountWei, txHash, await ethers.provider.getBlock('latest').then(b => b.timestamp + 1));
    });

    it("Should only allow operator to log trades", async function () {
      const tokenAddress = "0x532f27101965dd16442E59d40670FaF5eBB142E4";
      const action = "BUY";
      const decisionId = 1;
      const amountWei = ethers.parseEther("0.1");
      const txHash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef";

      await expect(
        antColony.connect(addr1).logExecution(decisionId, tokenAddress, action, amountWei, txHash)
      ).to.be.revertedWith("AntColony: not operator");
    });

    it("Should prevent double execution", async function () {
      const tokenAddress = "0x532f27101965dd16442E59d40670FaF5eBB142E4";
      const action = "BUY";
      const confidence = 7500;
      const signalCount = 100;
      const buyScore = 7500;
      const sellScore = 2500;

      // Log decision
      await antColony.logDecision(tokenAddress, action, confidence, signalCount, buyScore, sellScore);
      
      const decisionId = 1;
      const amountWei = ethers.parseEther("0.1");
      const txHash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef";

      // First execution should succeed
      await antColony.logExecution(decisionId, tokenAddress, action, amountWei, txHash);

      // Second execution should fail
      await expect(
        antColony.logExecution(decisionId, tokenAddress, action, amountWei, txHash)
      ).to.be.revertedWith("AntColony: already executed");
    });

    it("Should increment token trade count", async function () {
      const tokenAddress = "0x532f27101965dd16442E59d40670FaF5eBB142E4";
      const action = "BUY";
      const confidence = 7500;
      const signalCount = 100;
      const buyScore = 7500;
      const sellScore = 2500;

      expect(await antColony.tokenTradeCount(tokenAddress)).to.equal(0);

      // Log decision and execute
      await antColony.logDecision(tokenAddress, action, confidence, signalCount, buyScore, sellScore);
      const amountWei = ethers.parseEther("0.1");
      const txHash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef";
      await antColony.logExecution(1, tokenAddress, action, amountWei, txHash);

      expect(await antColony.tokenTradeCount(tokenAddress)).to.equal(1);
    });
  });

  describe("Admin Functions", function () {
    it("Should allow owner to update config", async function () {
      const newThreshold = 7000; // 70%
      const newSwarmSize = 150;

      await expect(
        antColony.updateConfig(newThreshold, newSwarmSize)
      )
        .to.emit(antColony, "SwarmConfigUpdated")
        .withArgs(newThreshold, newSwarmSize, await ethers.provider.getBlock('latest').then(b => b.timestamp + 1));

      expect(await antColony.consensusThreshold()).to.equal(newThreshold);
      expect(await antColony.swarmSize()).to.equal(newSwarmSize);
    });

    it("Should reject invalid threshold", async function () {
      await expect(
        antColony.updateConfig(4000, 100) // Below 50%
      ).to.be.revertedWith("AntColony: invalid threshold");

      await expect(
        antColony.updateConfig(11000, 100) // Above 100%
      ).to.be.revertedWith("AntColony: invalid threshold");
    });

    it("Should allow owner to pause and unpause", async function () {
      await antColony.pause();
      
      const tokenAddress = "0x532f27101965dd16442E59d40670FaF5eBB142E4";
      const action = "BUY";
      const confidence = 7500;
      const signalCount = 100;
      const buyScore = 7500;
      const sellScore = 2500;

      await expect(
        antColony.logDecision(tokenAddress, action, confidence, signalCount, buyScore, sellScore)
      ).to.be.revertedWithCustomError(antColony, "EnforcedPause");

      await antColony.unpause();
      
      await expect(
        antColony.logDecision(tokenAddress, action, confidence, signalCount, buyScore, sellScore)
      ).to.emit(antColony, "ColonyDecision");
    });
  });
});
