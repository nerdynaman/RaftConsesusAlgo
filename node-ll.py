import threading
import grpc
from grpc import StatusCode
from concurrent import futures
import concurrent.futures
from enum import Enum
import raft_pb2
import raft_pb2_grpc
import time

operations_client_requested = []
get_operations_answers = []
pending_operations = []
ip_port_to_nodeid_mapping = {}

class NodeType(Enum):
	LEADER = 1
	FOLLOWER = 2
	CANDIDATE = 3

class RaftNode:
	def check_metadata_file(self, Node_id):
		with open(f"logs_node_{Node_id}/metadata.txt", "r") as metadata_file:
			# Move cursor to the beginning of the file
			metadata_file.seek(0)
			lines = metadata_file.readlines()
			if(len(lines) == 0 or len(lines) == 1):
				return ""
			return lines[-1]
		
	def __init__(self, node_id:int , node_ip:str, node_port:int , node_type:NodeType):
		#node identifier
		self.node_id = node_id
		self.node_ip = node_ip
		self.node_port = node_port
		#p2p connections
		self.network = {} #dict of conn with peers in same cluster
		self.node_type = node_type
		#election
		if node_id == 1:
			self.election_timeout = 5
		elif node_id == 2:
			self.election_timeout = 6
		elif node_id == 3:
			self.election_timeout = 7
		elif node_id == 4:
			self.election_timeout = 8
		elif node_id == 5:
			self.election_timeout = 9
		self.election_timer = None
		self.current_term = 0
		self.last_voted_term = None
		self.vote_count = 0
		#leader
		self.heartbeat_timeout = 1
		self.heartbeat_timer = None
		# leader lease
		self.leader_lease_timeout = 4
		self.leader_lease = None
		#logs
		self.last_log_index = -1
		self.last_log_term = -1
		self.leader_commit = -1 
		metadata = self.check_metadata_file(self.node_id)
		if metadata != "":
			self.last_log_index, self.last_log_term, self.leader_commit, self.current_term = int(metadata.split()[-2]), int(metadata.split()[-1]), int(metadata.split()[0]), int(metadata.split()[1])
		self.array_next_index = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
		self.key_Value_calculator = {}
		self.logs = []
		self.start_election_timer()
		if node_id == 1:
			self.add_peer("127.0.0.1", 50052, 2)
			self.add_peer("127.0.0.1", 50053, 3)
			self.add_peer("127.0.0.1", 50054, 4)
			self.add_peer("127.0.0.1", 50055, 5)
		elif node_id == 2:
			self.add_peer("127.0.0.1", 50051, 1)
			self.add_peer("127.0.0.1", 50053, 3)
			self.add_peer("127.0.0.1", 50054, 4)
			self.add_peer("127.0.0.1", 50055, 5)
		elif node_id == 3:
			self.add_peer("127.0.0.1", 50051, 1)
			self.add_peer("127.0.0.1", 50052, 2)
			self.add_peer("127.0.0.1", 50054, 4)
			self.add_peer("127.0.0.1", 50055, 5)
		elif node_id == 4:
			self.add_peer("127.0.0.1", 50051, 1)
			self.add_peer("127.0.0.1", 50052, 2)
			self.add_peer("127.0.0.1", 50053, 3)
			self.add_peer("127.0.0.1", 50055, 5)
		elif node_id == 5:
			self.add_peer("127.0.0.1", 50051, 1)
			self.add_peer("127.0.0.1", 50052, 2)
			self.add_peer("127.0.0.1", 50053, 3)
			self.add_peer("127.0.0.1", 50054, 4)


	def generate_log_file(self, operations, term, Node_id, n_garbage):
		print("Generating log file", Node_id, operations)
		with open(f"logs_node_{Node_id}/logs.txt", "r") as log_file:
			# Move cursor to the beginning of the file
			log_file.seek(0)
			# Read existing content
			existing_content = log_file.readlines()
		with open(f"logs_node_{Node_id}/logs.txt", "w") as log_file:
			# If file is not empty, add a newline before appending new content
			if len(existing_content) != 0 and len(existing_content) - n_garbage != len(existing_content):
				del existing_content[len(existing_content) - n_garbage:]
			# Append new operations
			print(operations)
			for operation in range(len(operations)):
				if(operations[operation][:3] == "SET"):
					if len(operations[operation].split()) == 4:
						operations[operation] = (operations[operation])
					else:
						operations[operation] = (operations[operation] + " " + str(term) + "\n")
				else:
					if len(operations[operation].split()) == 2:
						operations[operation] = (operations[operation])
					else:
						operations[operation] = (operations[operation] + " " + str(term) + "\n")
			
			existing_content.extend(operations)
			operations = existing_content
			log_file.writelines(existing_content)
				# print(operation + " " + str(term) + "\n")
		print("Log file generated")
	
	def check_entry_value(self, Node_id, operation):
		write_entries = []
		with open(f"logs_node_{Node_id}/logs.txt", "r") as log_file:
			lines = log_file.readlines()
			# Reverse the lines list to read from the end of the file
			lines.reverse()
			for line in lines:
				if (line[:len(operation)] == operation):
					return line[len(operation):]
		return "Not found"
	
	def get_total_logs(self, Node_id):
		with open(f"logs_node_{Node_id}/logs.txt", "a+") as log_file:
			# Move cursor to the beginning of the file
			log_file.seek(0)
			# Read existing content
			existing_content = log_file.readlines()
			return len(existing_content)
	
	def generate_metadata_file(self, commit_length, term, node_id, last_log_index, last_log_term):
		with open(f"logs_node_{node_id}/metadata.txt", "a+") as metadata_file:
			# Move cursor to the beginning of the file
			metadata_file.seek(0)
			# Check if file is empty
			if not metadata_file.read(1):
				# If file is empty, write headers
				metadata_file.write("Commit_Length Term NodeID Last_Log_Index Last_Log_Term\n")
			# Append new metadata
			metadata_file.write(f"{commit_length} {term} {node_id} {last_log_index} {last_log_term}\n")
			
	def read_last_n_write_entries(self, Node_id, n):
		write_entries = []
		with open(f"logs_node_{Node_id}/logs.txt", "r") as log_file:
			lines = log_file.readlines()
			# Reverse the lines list to read from the end of the file
			write_entries.extend(lines[(len(lines) - n):])
		return write_entries
	
	def create_key_value_array(self, Node_id):
		with open(f"logs_node_{Node_id}/logs.txt", "r") as log_file:
			lines = log_file.readlines()
			for line in lines:
				if line[:3] == "SET":
					self.key_Value_calculator[line.split()[1]] = line.split()[2]
		return

	def add_peer(self, peer_ip:str, peer_port:int, node_id:int):
		# establish a grpc channel with the peer and add it to the network
		channel = grpc.insecure_channel(f"{peer_ip}:{peer_port}")
		self.network[(peer_ip, peer_port)] = channel
		ip_port_to_nodeid_mapping[(peer_ip, peer_port)] = node_id
		print("peer added success")

	def start_leader_lease_timer(self):
		# responsible for starting the leader lease timer
		if self.leader_lease:
			self.leader_lease.cancel()

		self.leader_lease = threading.Timer(self.leader_lease_timeout, lambda: None)
		self.leader_lease.endTime = time.time() + self.leader_lease_timeout
		self.leader_lease.start()
  
	def get_lease_duration(self):
		# return the remaining time for the leader lease to expire
		if self.leader_lease and self.leader_lease.is_alive():
			remaining_time = self.leader_lease.endTime - time.time()
			print("Remaining time:", remaining_time)
			if remaining_time > 0:
				return remaining_time
		return 0

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
	
	def send_heartbeat(self, first_op = False):
		# send heartbeat to all peers
		# TODO: Harshit look at this
		operations = []
		commit_counter = 0
		if(len(operations_client_requested) > 0) or self.leader_commit < self.last_log_index:
			print(f"first operationd client requested: {operations_client_requested} leader commit: {self.leader_commit} last log index: {self.last_log_index}")
			if len(operations_client_requested) > 0 and self.leader_commit == self.last_log_index: 
				print("first second")
				i = operations_client_requested[0]
				pending_operations.append(i)
				self.generate_log_file([i], self.current_term, self.node_id, 0)
				operations_client_requested.remove(i)
				# self.last_log_index += 1
				self.last_log_index = self.get_total_logs(self.node_id) - 1
				self.last_log_term = self.current_term
				self.generate_metadata_file(self.leader_commit, self.current_term, self.node_id, self.last_log_index, self.last_log_term)
			for peer in self.network:
				operations = []
				node_id_peer = ip_port_to_nodeid_mapping[peer]
				total_no_of_logs = self.get_total_logs(self.node_id)
				print(f"total no of logs: {total_no_of_logs}, node id peer: {node_id_peer}, array next index: {self.array_next_index[node_id_peer]}, last log index: {self.last_log_index}")
				logss_appended = self.read_last_n_write_entries(self.node_id, total_no_of_logs - self.array_next_index[node_id_peer] + 1)
				if total_no_of_logs - self.array_next_index[node_id_peer] + 1 > total_no_of_logs:
					logss_appended = self.read_last_n_write_entries(self.node_id, total_no_of_logs)
				print(f"Sending {logss_appended} to be appended to Node {self.node_id}")
				print("next index, peer", self.array_next_index[node_id_peer], node_id_peer)
				operations.extend(logss_appended)
				request = raft_pb2.Append_Entries(term=self.current_term, leaderId=str(self.node_id), prevLogIndex=self.last_log_index, prevLogTerm=self.last_log_term, entries=operations, leaderCommit=self.leader_commit)
				print("sending heartbeat")
				response = None
				response = self.send_append_entries(peer, request=request)
				print("RESPONSE: ", response)
				if response == True:
					commit_counter += 1
					self.array_next_index[node_id_peer] = self.last_log_index + 1
				elif response == False:
					if self.array_next_index[node_id_peer] != 0:
						self.array_next_index[node_id_peer] -= 1
				operations = []
			print(f"pending_operations {pending_operations}, self.leader_commit {self.leader_commit}, self.last_log_index {self.last_log_index}")
			if commit_counter >= (len(self.network) + 1)//2:
				if (self.leader_commit) < self.last_log_index and len(pending_operations) > 0:
					get_operations_answers.append(pending_operations[0] + " 1")
					self.key_Value_calculator[pending_operations[0].split()[-2]] = pending_operations[0].split()[-1]
					pending_operations.pop(0)
				self.leader_commit += 1
				self.generate_metadata_file(self.leader_commit, self.current_term, self.node_id, self.last_log_index, self.last_log_term)
			else:
				if len(pending_operations) > 0:
					get_operations_answers.append(pending_operations[0] + " 0")
			commit_counter = 0
		elif first_op == False:
			print("second")
			for peer in self.network:
				node_id_peer = ip_port_to_nodeid_mapping[peer]
				operations = []
				if self.array_next_index[node_id_peer] != self.leader_commit + 1:
					total_no_of_logs = self.get_total_logs(self.node_id)
					print(f"total no of logs: {total_no_of_logs}, node id peer: {node_id_peer}, array next index: {self.array_next_index[node_id_peer]}, last log index: {self.last_log_index}")
					logss_appended = self.read_last_n_write_entries(self.node_id, total_no_of_logs - self.array_next_index[node_id_peer] + 1)
					operations.extend(logss_appended)
					print("LOGS BEING SENT ARE", operations)
				request = raft_pb2.Append_Entries(term=self.current_term, leaderId=str(self.node_id), prevLogIndex=self.last_log_index, prevLogTerm=self.last_log_term, entries=operations, leaderCommit=self.leader_commit)
				send_success = self.send_append_entries(peer, request=request)
				if self.array_next_index[node_id_peer] != self.leader_commit + 1 and send_success == True:
					self.array_next_index[node_id_peer] = self.leader_commit + 1
				elif send_success == True :
					self.array_next_index[node_id_peer] = self.last_log_index + 1
				elif send_success == False:
					if self.array_next_index[node_id_peer] > 0: 
						self.array_next_index[node_id_peer] -= 1
		else:
			print("third")
			self.generate_log_file(["NO-OP"], self.current_term, self.node_id, 0)
			# self.last_log_index += 1 
			self.last_log_index = self.get_total_logs(self.node_id) - 1
			self.last_log_term = self.current_term
			for peer in self.network:
				node_id_peer = ip_port_to_nodeid_mapping[peer]
				request = raft_pb2.Append_Entries(term=self.current_term, leaderId=str(self.node_id), prevLogIndex=self.last_log_index, prevLogTerm=self.last_log_term, entries=["NO-OP"], leaderCommit=self.leader_commit)
				response = self.send_append_entries(peer, request=request)
				if response == True :
					commit_counter += 1
					self.array_next_index[node_id_peer] = self.last_log_index + 1
				else :
					print("failed")
				print("sending heartbeat")
			if commit_counter >= (len(self.network) + 1)//2:
				self.leader_commit += 1
			self.generate_metadata_file(self.leader_commit, self.current_term, self.node_id, self.last_log_index, self.last_log_term)

		self.start_heartbeat_timer()


	def start_election(self):
		if self.get_lease_duration() > 0: # NOTE: this condition will never hit
			return
		self.vote_count = 0
		if self.node_type == NodeType.LEADER:
			self.start_election_timer()
			return
		self.current_term += 1
		self.node_type = NodeType.CANDIDATE
		self.vote_count += 1
		self.last_voted_term = self.current_term
		leaseArr = []
		for peer in self.network:
			# send request vote to all peers
			leaseDuration = self.send_request_vote(peer)
			leaseArr.append(leaseDuration)
			print("request vote sent to " + str(peer))
		# now restart the election timer
		# vote for self
		if self.vote_count > (len(self.network)+1)//2:
			self.node_type = NodeType.LEADER
			for i in self.array_next_index:
				self.array_next_index[i] = self.get_total_logs(self.node_id)
			self.create_key_value_array(self.node_id)
			self.start_heartbeat_timer()
			self.send_heartbeat(True)
			self.start_leader_lease_timer()

		self.start_election_timer()

	def send_request_vote(self, peer:tuple):
		# channel = self.network[peer[0], peer[1]]
		channel = grpc.insecure_channel(f"{peer[0]}:{peer[1]}")
		stub = raft_pb2_grpc.RaftStub(channel)
		print("stub created")
		# compressing the request by calling Request_Vote mentioned in Raft.proto
		# TODO: Harsh look at this and correct the values in last log index and last log term in request section
		request = raft_pb2.Request_Vote(term=self.current_term, candidateId=str(self.node_id), lastLogIndex=self.last_log_index, lastLogTerm=self.last_log_term)
		print("request created")
		try:
			response = stub.RequestVote(request)
		except grpc.RpcError as e:
			print("error: ", e)
			return
		if (response.voteGranted) and response.leaseDuration <= 0:
			self.vote_count += 1
		if response.term > self.current_term:
			self.current_term = response.term
		print(response)
		return response.leaseDuration

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
			if self.heartbeat_timer:
				self.heartbeat_timer.cancel
		if request.term > self.current_term:
			self.current_term = request.term
		response.leaseDuration = self.get_lease_duration()
		self.start_election_timer()
		print(response)
		return response

	def AppendEntries(self, request, context):
		print("AppendEntries called")
		print(request.entries)
		print(get_operations_answers)
		self.start_election_timer()
		operations = []
		response = raft_pb2.AppendEntriesResponse()
		if request.term > self.current_term:
			self.current_term = request.term
			# self.generate_metadata_file(self.leader_commit, self.current_term, self.node_id, self.last_log_index, self.last_log_term)

		if request.term < self.current_term:
			print(f"1 append entries, request.term: {request.term}, self.current_term: {self.current_term}")
			response.success = False
			response.term = self.current_term
			# self.generate_metadata_file(self.leader_commit, self.current_term, self.node_id, self.last_log_index, self.last_log_term)
		# elif TODO: Harshit implement the rest of the logic
		elif self.node_type == NodeType.LEADER:
			print(2)
			response.success = False
			response.term = self.current_term
			# self.generate_metadata_file(self.leader_commit, self.current_term, self.node_id, self.last_log_index, self.last_log_term)
		elif len(request.entries) == 0:
			print(3)
			self.current_term = request.term
			self.node_type = NodeType.FOLLOWER
			self.last_voted_term = request.term
			self.start_election_timer()
			response.success = True
			response.term = self.current_term
			self.leader_commit = request.leaderCommit
			# self.generate_metadata_file(self.leader_commit, self.current_term, self.node_id, self.last_log_index, self.last_log_term)
		elif self.last_log_index < request.prevLogIndex:
			print(4)
			self.current_term = request.term
			self.node_type = NodeType.FOLLOWER
			self.last_voted_term = request.term
			self.start_election_timer()
			response.success = True
			response.term = self.current_term
			self.leader_commit = request.leaderCommit

			print("Adding entry to log file")
			n_garbage = 1
			current_logs = self.read_last_n_write_entries(self.node_id, n_garbage)
			while len(current_logs) > 0 and len(request.entries) > 0 and current_logs[0] != request.entries[0] and len(current_logs) == n_garbage:
			# while current_logs[0] != request.entries[0] and len(current_logs) == n_garbage:
				n_garbage += 1
				current_logs = self.read_last_n_write_entries(self.node_id, n_garbage)
			if len(request.entries) > 0 and len(current_logs) < n_garbage:
				print(4, 2)
				if self.last_log_index == -1:
					operations.extend(request.entries)
					self.generate_log_file(operations, self.current_term, self.node_id, len(current_logs))
					# self.last_log_index = len(operations) - 1
					self.last_log_index = self.get_total_logs(self.node_id) - 1
					self.last_log_term = self.current_term
					self.leader_commit = request.leaderCommit
					# instead if generate log file use compare and update entries
					print(response)
					self.generate_metadata_file(self.leader_commit, self.current_term, self.node_id, self.last_log_index, self.last_log_term)
					return response
				else:
					print(4, 3)
					response.success = False
					if len(request.entries) == (request.prevLogIndex + 1):
						response.success = True
						self.generate_log_file(request.entries, self.current_term, self.node_id, (self.get_total_logs(self.node_id)))
						self.leader_commit = request.leaderCommit
						self.last_log_index = self.get_total_logs(self.node_id) - 1
						self.last_log_term = self.current_term
					response.term = self.current_term
					print(response)
					self.generate_metadata_file(self.leader_commit, self.current_term, self.node_id, self.last_log_index, self.last_log_term)
					return response
			# # AppendEntries code ended
			# elif len(request.entries) == 0:
			# 	operations.append("NO-OP")``
			# 	self.generate_log_file(operations, self.current_term, self.node_id, n_garbage - 1)	
			# 	print(response)
			# 	return response			
			# print("#3")
			operations.extend(request.entries[1:])
			self.generate_log_file(operations, self.current_term, self.node_id, n_garbage - 1)
			# self.last_log_index += len(operations)-1
			self.last_log_index = self.get_total_logs(self.node_id) - 1
			self.last_log_term = self.current_term
			self.leader_commit = request.leaderCommit
		else:
			print(5)
			response.success = False
			if self.last_log_index == request.prevLogIndex and self.last_log_term == request.prevLogTerm:
				response.success = True
			if len(request.entries) == (request.prevLogIndex + 1):
				response.success = True
				self.generate_log_file(request.entries, self.current_term, self.node_id, (self.get_total_logs(self.node_id)))
				self.leader_commit = request.leaderCommit
				self.last_log_index = self.get_total_logs(self.node_id) - 1
				self.last_log_term = self.current_term
			response.term = self.current_term
			# self.leader_commit = request.leaderCommit
		self.start_leader_lease_timer()
		print(response)
		self.generate_metadata_file(self.leader_commit, self.current_term, self.node_id, self.last_log_index, self.last_log_term)
		return response

	def send_append_entries(self, peer:tuple, request=None):
		# channel = self.network[peer[0], peer[1]]
		channel = grpc.insecure_channel(f"{peer[0]}:{peer[1]}")
		stub = raft_pb2_grpc.RaftStub(channel)
		# compressing the request by calling Append_Entries mentioned in Raft.proto
		if not request:
			# TODO: Harsh look at this
			request = raft_pb2.Append_Entries(term=self.current_term, leaderId=str(self.node_id), prevLogIndex=self.last_log_index, prevLogTerm=self.last_log_term, entries=[], leaderCommit=self.leader_commit)
		try:
			response = stub.AppendEntries(request)
			# DO response check
		except grpc.RpcError as e:
			print("error ", e)
			return None
		print("response success", response.success)
		return response.success
	
	def get_value_from_database(self, key):
		# get value from database
		# op_string = f"GET {key}"
		if key not in self.key_Value_calculator:
			return "Key not found"
		value = self.key_Value_calculator[str(key)]
		return value

	def set_value_to_database(self, key, value):
		# set value to database
		op_string = f"SET {key} {value}"
		get_operations_answers.clear()
		operations_client_requested.append(f"SET {key} {value}")
		answer = None
		while answer == None:
			for i in get_operations_answers:
				if i[:len(op_string)] == op_string:
					answer = bool(int(i[-1]))
					get_operations_answers.remove(i)
					break
		return answer

	def ServeClient(self, request, context):
			print(f"ServeClient called {self.node_id}")
			# response = raft_pb2.ServeClientResponse()

			operation = request.Request.strip().split()

			# check if the node is the leader
			if self.node_type != NodeType.LEADER:
					return raft_pb2.ServeClientResponse(Data="INCORRECT Leader", LeaderID=str(self.node_id), Success=False)

			if operation[0] == "GET":
					key = operation[1]
					# NOTE: Harshit implement this
					value = self.get_value_from_database(key)
					return raft_pb2.ServeClientResponse(Data=value, LeaderID=str(self.node_id), Success=True)
			elif operation[0] == "SET":
					key, value = operation[1], operation[2]
					# NOTE: Harshit implement this
					self.set_value_to_database(key, value)
					return raft_pb2.ServeClientResponse(Data="SET operation successful", LeaderID=str(self.node_id), Success=True)
			else:
					return raft_pb2.ServeClientResponse(Data="INVALID operation", LeaderID=str(self.node_id), Success=False)

	def _str_(self):
		return f"Node ID: {self.node_id}, Node IP: {self.node_ip}, Node Port: {self.node_port}, Node Type: {self.node_type}"

	def _repr_(self):
		return f"Node ID: {self.node_id}, Node IP: {self.node_ip}, Node Port: {self.node_port}, Node Type: {self.node_type}"



# python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. raft.proto
	
		

def startNode(nodeId:int, nodeIp:str, nodePort:int, nodeType:NodeType):
	# making grpc connections
	server = grpc.server(concurrent.futures.ThreadPoolExecutor(max_workers=10))
	raft_pb2_grpc.add_RaftServicer_to_server(RaftNode(nodeId,"127.0.0.1", nodePort, nodeType), server)
	server.add_insecure_port(f"[::]:{nodePort}")
	server.start()
	server.wait_for_termination()



# python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. raft.proto
	
if __name__ == "__main__":
	userInput = int(input("Enter the node id: "))
	if userInput == 1:
		startNode(1, "127.0.0.1", 50051, NodeType.FOLLOWER)
	elif userInput == 2:
		startNode(2, "127.0.0.1", 50052, NodeType.FOLLOWER)
	elif userInput == 3:
		startNode(3, "127.0.0.1", 50053, NodeType.FOLLOWER)
	elif userInput == 4:
		startNode(4, "127.0.0.1", 50054, NodeType.FOLLOWER)
	elif userInput == 5:
		startNode(5, "127.0.0.1", 50055, NodeType.FOLLOWER)
	elif userInput == 9:
		with open("logs_node_1/logs.txt", "w") as log_file:
			pass
		with open("logs_node_2/logs.txt", "w") as log_file:
			pass
		with open("logs_node_3/logs.txt", "w") as log_file:
			pass
		with open("logs_node_4/logs.txt", "w") as metadata_file:
			pass
		with open("logs_node_5/logs.txt", "w") as metadata_file:
			pass
		with open("logs_node_1/metadata.txt", "w") as metadata_file:
			pass
		with open("logs_node_2/metadata.txt", "w") as metadata_file:
			pass
		with open("logs_node_3/metadata.txt", "w") as metadata_file:
			pass
		with open("logs_node_4/metadata.txt", "w") as metadata_file:
			pass
		with open("logs_node_5/metadata.txt", "w") as metadata_file:
			pass
