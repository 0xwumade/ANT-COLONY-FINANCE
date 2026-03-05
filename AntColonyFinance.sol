// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title AntColonyFinance
 * @notice Onchain audit log for swarm trading decisions on Base
 *
 * This contract:
 * 1. Logs every ColonyDecision onchain (immutable audit trail)
 * 2. Tracks performance metrics per token
 * 3. Allows the colony operator to pause/resume in emergencies
 *
 * Deployed on Base — qualifies for CDP Builder Grants program
 * (uses Base + emits onchain data readable by CDP tools)
 */

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

contract AntColonyFinance is Ownable, Pausable {

    // ── Events ────────────────────────────────────────────────────────

    event ColonyDecision(
        uint256 indexed decisionId,
        address indexed token,
        string  action,          // "BUY" | "SELL" | "HOLD"
        uint256 confidence,      // scaled ×10000 (e.g. 6500 = 65.00%)
        uint256 signalCount,
        uint256 buyScore,        // scaled ×10000
        uint256 sellScore,       // scaled ×10000
        uint256 timestamp
    );

    event TradeExecuted(
        uint256 indexed decisionId,
        address indexed token,
        string  action,
        uint256 amountWei,
        bytes32 txHash,
        uint256 timestamp
    );

    event SwarmConfigUpdated(
        uint256 newThreshold,
        uint256 newSwarmSize,
        uint256 timestamp
    );

    // ── State ─────────────────────────────────────────────────────────

    uint256 public decisionCount;
    uint256 public consensusThreshold;  // e.g. 6500 = 65%
    uint256 public swarmSize;
    address public colonyOperator;      // the Python backend wallet

    // token → trade count
    mapping(address => uint256) public tokenTradeCount;
    // decisionId → was executed
    mapping(uint256 => bool) public decisionExecuted;

    // ── Constructor ───────────────────────────────────────────────────

    constructor(
        address _operator,
        uint256 _threshold,
        uint256 _swarmSize
    ) Ownable(msg.sender) {
        colonyOperator    = _operator;
        consensusThreshold = _threshold;
        swarmSize         = _swarmSize;
    }

    // ── Modifiers ─────────────────────────────────────────────────────

    modifier onlyOperator() {
        require(
            msg.sender == colonyOperator || msg.sender == owner(),
            "AntColony: not operator"
        );
        _;
    }

    // ── Core Functions ────────────────────────────────────────────────

    /**
     * @notice Log a swarm consensus decision onchain
     * @param token       ERC-20 token address
     * @param action      "BUY", "SELL", or "HOLD"
     * @param confidence  Confidence score (scaled ×10000)
     * @param signalCount Number of agent signals that voted
     * @param buyScore    Aggregated buy score (scaled ×10000)
     * @param sellScore   Aggregated sell score (scaled ×10000)
     */
    function logDecision(
        address token,
        string  calldata action,
        uint256 confidence,
        uint256 signalCount,
        uint256 buyScore,
        uint256 sellScore
    ) external onlyOperator whenNotPaused returns (uint256 decisionId) {
        decisionId = ++decisionCount;

        emit ColonyDecision(
            decisionId,
            token,
            action,
            confidence,
            signalCount,
            buyScore,
            sellScore,
            block.timestamp
        );

        return decisionId;
    }

    /**
     * @notice Record a trade execution after the swap
     * @param decisionId  The decision this trade corresponds to
     * @param token       Token address
     * @param action      "BUY" or "SELL"
     * @param amountWei   Trade size in wei
     * @param txHash      The swap transaction hash
     */
    function logExecution(
        uint256 decisionId,
        address token,
        string  calldata action,
        uint256 amountWei,
        bytes32 txHash
    ) external onlyOperator whenNotPaused {
        require(!decisionExecuted[decisionId], "AntColony: already executed");
        decisionExecuted[decisionId] = true;
        tokenTradeCount[token]++;

        emit TradeExecuted(
            decisionId,
            token,
            action,
            amountWei,
            txHash,
            block.timestamp
        );
    }

    // ── Admin Functions ───────────────────────────────────────────────

    function updateConfig(
        uint256 newThreshold,
        uint256 newSwarmSize
    ) external onlyOwner {
        require(newThreshold > 5000 && newThreshold <= 10000, "AntColony: invalid threshold");
        consensusThreshold = newThreshold;
        swarmSize          = newSwarmSize;
        emit SwarmConfigUpdated(newThreshold, newSwarmSize, block.timestamp);
    }

    function setOperator(address newOperator) external onlyOwner {
        colonyOperator = newOperator;
    }

    function pause()   external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }
}
