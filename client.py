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
                return response.Data, response.LeaderID, response.Success
            else:
                if response.Data == "INCORRECT Leader":
                    print(f"FAIL: Node {response.LeaderID} is not the leader")
                elif response.Data == "INVALID operation":
                    print(f"FAIL: Invalid {request} operation")
        except grpc.RpcError:
            print(f"FAIL: Node {self.leader_id} is not the leader")
    
    def serve_client(self, request):
        if self.leader_id is not None:
            self.check_leader(request=request)
            
        
        for address in self.node_addresses:
            channel = grpc.insecure_channel(address)
            print(f"Trying to connect to {address}")
            stub = raft_pb2_grpc.RaftStub(channel)
            try:
                response = stub.ServeClient(raft_pb2.Serve_Client(Request=request))
                print(response)
                self.leader_id = response.LeaderID # Update leader_id
                self.check_leader(request)
                if response.Success:
                    return response.Data, response.LeaderID, response.Success
                else:
                    if response.Data == "INCORRECT Leader":
                        print(f"FAIL: Node {response.LeaderID} is not the leader")
                    elif response.Data == "INVALID operation":
                        print(f"FAIL: Invalid {request} operation")
            except grpc.RpcError:
                print(f"FAIL: Node {address} is not reachable - RpcError")
        return None, None, False

def main():
    node_addresses = ['127.0.0.1:50051', '127.0.0.1:50052', '127.0.0.1:50053', '127.0.0.1:50054', '127.0.0.1:50055']  # Example addresses
    client = RaftClient(node_addresses)

    while True:
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