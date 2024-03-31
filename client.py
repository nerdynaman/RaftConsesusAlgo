import grpc
import raft_pb2
import raft_pb2_grpc

class RaftClient:
    def __init__(self, node_addresses):
        self.node_addresses = node_addresses
        self.leader_id = None

    def get_leader_address(self):
      return self.node_addresses[int(self.leader_id) - 1]


    def check_leader(self,request):
        leader_address = self.get_leader_address()
        channel = grpc.insecure_channel(leader_address)
        stub = raft_pb2_grpc.RaftStub(channel)
        try:
            response = stub.ServeClient(raft_pb2.Serve_Client(Request=request))
            if response.Success:
                self.leader_id = response.LeaderID
                print(f"Leader IS {self.leader_id}")
                return response
            else:
                if response.LeaderID != self.leader_id:
                    self.leader_id = response.LeaderID
                else:
                    self.leader_id = None
                if response.Data == "INCORRECT Leader":
                    print(f"FAIL1: Node {self.leader_id} is not the leader")
                elif response.Data == "INVALID operation":
                    print(f"FAIL: Invalid {request} operation")
            return response
        except grpc.RpcError:
            self.leader_id = None
            print(f"FAIL2: Node {self.leader_id} is not the leader")
            return None
    
    def serve_client(self, request):
        print("Leader ID: ", self.leader_id)
        if self.leader_id is not None:
            response = self.check_leader(request=request)
            if response is not None and response.Success:
                return response.Data, response.LeaderID, response.Success
        # now we need to find the leader and every time we request a node it will return the expected leader
            
        for i in range(len(self.node_addresses)):
            if self.leader_id is not None:
                channel = grpc.insecure_channel(self.get_leader_address())
            else:
                channel = grpc.insecure_channel(self.node_addresses[i])
            stub = raft_pb2_grpc.RaftStub(channel)
            try:
                response = stub.ServeClient(raft_pb2.Serve_Client(Request=request))
                if response.Success:
                    self.leader_id = response.LeaderID
                    return response.Data, response.LeaderID, response.Success
                else:
                    self.leader_id = response.LeaderID
                    if response.Data == "INCORRECT Leader":
                        print(f"FAIL3: Node {i+1} is not the leader")
                    elif response.Data == "INVALID operation":
                        print(f"FAIL: Invalid {request} operation")
                    if self.leader_id == i+1:
                        self.leader_id = None
            except grpc.RpcError:
                print(f"FAIL4: Node {i+1} is not the leader")

        

        return None, None, False

def main():
    node_addresses = ['10.190.0.2:50051', '10.190.0.3:50052', '10.190.0.4:50053', '10.190.0.5:50054', '10.190.0.6:50055']  # Example addresses
    client = RaftClient(node_addresses)

    while True:
        print(client.leader_id, "leader")
        operation = input("Enter operation (GET/SET key value): ")
        if operation.lower().startswith('set'):
            _, key, value = operation.split()
            response_data, leader_id, success = client.serve_client(f"SET {key} {value}")
        elif operation.lower().startswith('get'):
            _, key = operation.split()
            response_data, leader_id, success = client.serve_client(f"GET {key}")
        else:
            print("Invalid operation. Please enter GET or SET operation.")
            continue
        
        if success:
            print(f"Operation successful. Response: {response_data}")
        else:
            print(f"Operation failed. Current leader: {leader_id}")

if __name__ == "__main__":
    main()