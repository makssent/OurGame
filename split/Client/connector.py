import socket


def connect_to_server(server_ip='127.0.0.1', port=65432): # Коннект к серверу
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
        client_socket.connect((server_ip, port))
        print(f"Подключение к серверу {server_ip}:{port} установлено")

        data = client_socket.recv(1024)
        print(f"Получено от сервера: {data.decode()}")

if __name__ == "__main__":
    connect_to_server()