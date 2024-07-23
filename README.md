# Raft Implementation
This project is a comprehensive implementation of the Raft consensus algorithm in Python. Raft is designed to provide a robust, fault-tolerant mechanism for managing replicated logs across multiple servers. It ensures that all nodes agree on the values stored in the log, even in the presence of failures.

# Entities
1) Node: It is a replicated state machine. Each node can take on one of three roles—leader, follower, or candidate—and works together with other nodes to ensure data consistency and fault tolerance in a distributed system. Along with serving client requests when in leader status otherwise processing appendentries.
2) gRPC: It is responsible for all the communication between nodes such as sending client requests, append entries between nodes, leader election messages.

# Features
1) Leader Election: Implements the leader election process where one node is elected as the leader among the peers.
2) Log Replication: Ensures that the leader's log entries are replicated across all follower nodes.
3) Safety: Guarantees safety properties such as election safety, log matching, and state machine safety.
4) Fault Tolerance: Designed to handle failures gracefully, ensuring system availability and consistency.
5) Linearizable Reads: Supports linearizable reads from the leader, providing strong consistency guarantees.
6) Snapshotting: Includes snapshotting functionality to compact the log and improve performance.
