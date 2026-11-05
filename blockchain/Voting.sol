pragma solidity ^0.8.0;

contract Voting {
    mapping(address => bool) public allowed;
    mapping(address => bool) public voted;
    uint256 public approveVotes;
    uint256 public rejectVotes;
    uint256 public requiredVotes;
    bool public ended;
    bool public approved;
    event VotingEnded(bool approved);

    constructor(address[] memory voters) {
        requiredVotes = voters.length / 2 + 1;
        for (uint256 i = 0; i < voters.length; i++) {
            allowed[voters[i]] = true;
        }
    }

    function vote(bool approve) public {
        require(!ended, "Voting ended.");
        require(allowed[msg.sender], "Invalid address.");
        require(!voted[msg.sender], "Already voted.");
        voted[msg.sender] = true;
        if (approve) { approveVotes++; } else { rejectVotes++; }
        if (approveVotes >= requiredVotes || rejectVotes >= requiredVotes) {
            ended = true;
            approved = approveVotes >= requiredVotes;
            emit VotingEnded(approved);
        }
    }
}
