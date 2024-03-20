import threading
import grpc
from grpc import StatusCode
from concurrent import futures
import concurrent.futures
from enum import Enum
import raft_pb2
import raft_pb2_grpc

class NodeType(Enum):
	LEADER = 1
	FOLLOWER = 2
	CANDIDATE = 3

class RaftNode:
	def __init__(self, node_id:int , node_ip:str, node_port:int , node_type:NodeType):
		# node identifier
		self.node_id = node_id
		self.node_ip = node_ip
		self.node_port = node_port
		# p2p connections
		self.network = {} # dict of conn with peers in same cluster
		self.node_type = node_type
		# election
		self.election_timeout = 5
		self.election_timer = None
		self.current_term = 0
		self.last_voted_term = None
		self.vote_count = 0
		# leader
		self.heartbeat_timeout = 1
		self.heartbeat_timer = None
		# logs
		self.last_log_index = 0
		self.last_log_term = 0
		self.start_election_timer()
		self.add_peer("127.0.0.1", 50051)
		self.add_peer("127.0.0.1", 50053)
		# self.add_peer("127.0.0.1", 50052)

	def add_peer(self, peer_ip:str, peer_port:int):
		# establish a grpc channel with the peer and add it to the network
		channel = grpc.insecure_channel(f"{peer_ip}:{peer_port}")
		self.network[(peer_ip, peer_port)] = channel
		print("peer added success")

	def start_election_timer(self):
		# responsible for starting the timer for each node
		if self.election_timer:
			self.election_timer.cancel()

		# generate a random election timeout
		self.election_timer = threading.Timer(self.election_timeout, self.start_election)
		self.election_timer.start()
	
	def start_heartbeat_timer(self):
		# responsible for starting the timer for each node
		if self.heartbeat_timer:
			self.heartbeat_timer.cancel()

		# generate a random election timeout
		self.heartbeat_timer = threading.Timer(self.heartbeat_timeout, self.send_heartbeat)
		self.heartbeat_timer.start()
	
	def send_heartbeat(self):
		# send heartbeat to all peers
		# TODO: Harshit look at this
		request = raft_pb2.Append_Entries(term=self.current_term, leaderId=str(self.node_id), prevLogIndex=self.last_log_index, prevLogTerm=self.last_log_term, entries=[], leaderCommit=0)
		for peer in self.network:
			print("sending heartbeat")
			self.send_append_entries(peer,request=request)
		self.start_heartbeat_timer()

	def start_election(self):
		self.vote_count = 0
		if self.node_type == NodeType.LEADER:
			self.start_election_timer()
			return
		self.current_term += 1
		self.node_type = NodeType.CANDIDATE
		self.vote_count += 1
		self.last_voted_term = self.current_term
		for peer in self.network:
			# send request vote to all peers
			self.send_request_vote(peer)
			print("request vote sent to " + str(peer))
		# now restart the election timer
		# vote for self
		if self.vote_count > (len(self.network)+1)/2:
			self.node_type = NodeType.LEADER
			self.start_heartbeat_timer()
			self.send_heartbeat()

		self.start_election_timer()

	def send_request_vote(self, peer:tuple):
		channel = self.network[peer[0], peer[1]]
		stub = raft_pb2_grpc.RaftStub(channel)
		print("stub created")
		# compressing the request by calling Request_Vote mentioned in Raft.proto
		# TODO: Harshit look at this
		request = raft_pb2.Request_Vote(term=self.current_term, candidateId=str(self.node_id), lastLogIndex=0, lastLogTerm=0)
		print("request created")
		try:
			response = stub.RequestVote(request)
		except grpc.RpcError as e:
			return
		if (response.voteGranted):
			self.vote_count += 1
		if response.term > self.current_term:
			self.current_term = response.term
		print(response)

	def RequestVote(self,request, context):
		print("RequestVote called")
		response = raft_pb2.RequestVoteResponse()
		if self.current_term == self.last_voted_term:
			response.voteGranted = False
			response.term = self.current_term
		elif request.term < self.current_term:
			response.voteGranted = False
			response.term = self.current_term
		elif request.lastLogTerm < self.last_log_term:
			response.success = False
			response.term = self.current_term
		elif request.lastLogIndex < self.last_log_index:
			response.success = False
			response.term = self.current_term
		else:
			self.node_type = NodeType.FOLLOWER
			self.last_voted_term = request.term
			response.voteGranted = True
			response.term = self.current_term
		if request.term > self.current_term:
			self.current_term = request.term
		self.start_election_timer()
		print(response)
		return response

	def AppendEntries(self, request, context):
		print("AppendEntries called")
		self.start_election_timer()
		response = raft_pb2.AppendEntriesResponse()
		if request.term > self.current_term:
			self.current_term = request.term
		if request.term < self.current_term:
			response.success = False
			response.term = self.current_term
		# elif TODO: Harshit implement the rest of the logic
		elif self.node_type == NodeType.LEADER:
			response.success = False
			response.term = self.current_term
		else:
			self.current_term = request.term
			self.node_type = NodeType.FOLLOWER
			self.last_voted_term = request.term
			self.start_election_timer()
			response.success = True
			response.term = self.current_term
		print(response)
		return response

	def send_append_entries(self, peer:tuple, request=None):
		channel = self.network[peer[0], peer[1]]
		stub = raft_pb2_grpc.RaftStub(channel)
		# compressing the request by calling Append_Entries mentioned in Raft.proto
		if not request:
			# TODO: Harshit look at this
			request = raft_pb2.Append_Entries(term=self.current_term, leaderId=str(self.node_id), prevLogIndex=0, prevLogTerm=0, entries=[], leaderCommit=0)
		try:
			response = stub.AppendEntries(request)
		except grpc.RpcError as e:
			return
		print(response)



	def __str__(self):
		return f"Node ID: {self.node_id}, Node IP: {self.node_ip}, Node Port: {self.node_port}, Node Type: {self.node_type}"

	def __repr__(self):
		return f"Node ID: {self.node_id}, Node IP: {self.node_ip}, Node Port: {self.node_port}, Node Type: {self.node_type}"
	

def startNode():
	# making grpc connections
	server = grpc.server(concurrent.futures.ThreadPoolExecutor(max_workers=10))
	raft_pb2_grpc.add_RaftServicer_to_server(RaftNode(2,"127.0.0.1", 50052, NodeType.FOLLOWER), server)
	server.add_insecure_port("[::]:50052")
	server.start()
	server.wait_for_termination()



# python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. raft.proto
	
if __name__ == "__main__":
	startNode()
	# node = RaftNode(1, "127.0.0.1", 50051, NodeType.LEADER)
	# node.add_peer("127.0.0.1", 50052)
	# node.send_request_vote(node.network[0])