# BARAN KANAT - 22100011013

### Kutuphaneler ###
import socket
import sys
import threading
### Kutuphaneler ###

### Istemci Bilgileri ###
HOST = '127.0.0.1'
PORT = 12345
BUFFER_SIZE = 1024
### Istemci Bilgileri ###

### Durum Değişkeni ###
isRunning = True
role = ""
### Durum Değişkeni ###


### Fonksiyonlar ###

#----- Neden Mesaj Almak ve Mesaj Gondermek Icın Thread kullandım? -----#
# SendTCP ile hem gelen mesajlari dinlemek hemde mesajlari gonderebilmek icin 2 'while Dongusu' kullandim.
# Boylelikle surekli olarak mesaj alabilecek ve mesaj atabilecektim. Ancak 2 'while dongusu' oldugu icin
#   bir dongu bitmeden ikincisine gecemedigim icin ya mesajlasmayi bitirecektim ya da mesaj almayi bitirmem gerekiyordu.
# Bu problemi de birbirinden bagimsiz 2 thread kullanmakta buldum. Bu sayede surekli olarak hem sunucudan gelebilecek
#   mesajlari okuyabilirim. Hemde istedigim zaman mesaj gonderebilirim.

def messageReceive(sock):
    global isRunning
    while isRunning:
        try:
            mesaj = sock.recv(BUFFER_SIZE).decode()
            if mesaj:
                print(f"\n{mesaj}")
                if "doktor bulunmamaktadır" in mesaj:
                    print("Doktor olmadığı için bağlantınız kapatılıyor. lütfen Enter'a basarak çıkın...")
                    isRunning = False
                    sock.close()
                    break

                elif "Geçmiş Olsun" in mesaj:
                    print("lütfen Enter'a basarak çıkın...")
                    isRunning = False
                    sock.close()
                    break

                elif "tedavi hakkini" in mesaj:
                    print("Farkli bir gunde tekrar geliniz, lütfen Enter'a basarak çıkın...")
                    isRunning = False
                    sock.close()
                    break

                elif "Bekleyen hasta bulunmamaktadır" in mesaj:
                    print("Tüm randevular bitti. Oturum kapatılıyor. Lütfen Enter'a basarak çıkın...")
                    isRunning = False
                    sock.close()
                    break


            else:
                break
        except:
            break


def userInput(sock):
    global isRunning

    while isRunning:
        try:
            mesaj = input("Mesajin: ")

            # Baglanti kapatma komutu
            if mesaj == "XXX":
                isRunning = False
                sock.sendall(mesaj.encode())
                sock.close()
                break


            sock.sendall(mesaj.encode())
        except:
            break


def sendTCP(role):
    global isRunning
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client_socket.connect((HOST, PORT))

        client_socket.sendall(role.encode())

        thread_recv = threading.Thread(target=messageReceive, args=(client_socket,))
        thread_recv.start()

        thread_input = threading.Thread(target=userInput, args=(client_socket,))
        thread_input.start()

        thread_recv.join()
        thread_input.join()

    except ConnectionRefusedError:
        print("[HATA] Sunucuya bağlanılamadı.")


#--- UDP Baglantisi ---#
def udp_input(udp_sock):
    global isRunning
    while isRunning:
        try:
            mesaj = input("Mesajin: ")
            udp_sock.sendto(mesaj.encode(), (HOST, PORT))
            if mesaj == "XXX":
                isRunning = False
                break   # Buradan dongden cikiliyor
        except:
            break


def udp_receive(udp_sock):
    global isRunning

    while isRunning:
        try:
            # 1. Veri al
            data, addr = udp_sock.recvfrom(BUFFER_SIZE)

            # 2. Mesajı decode et
            msg = data.decode()

            # 3. Mesajı ekrana yazdır
            print(f"{msg}")

            # 4. Eğer mesajda "Geçmiş Olsun" geçiyorsa çık
            if "Geçmiş Olsun" in msg:
                print("Çıkmak için Enter’a basın...")
                isRunning = False

            elif "doktor bulunmamaktadır" in msg:
                print("Doktor olmadığı için bağlantınız kapatılıyor. lütfen Enter'a basarak çıkın...")
                isRunning = False

                # Soketi kapat
                udp_sock.close()
                break

            elif "tedavi hakkini" in msg:
                print("Farkli bir gunde tekrar geliniz, lütfen Enter'a basarak çıkın...")
                isRunning = False

                udp_sock.close()
                break

        except Exception as e:
            print(f"[HATA] Mesaj alınırken hata oluştu: {e}")
            break




def sendUDP(role):
    global isRunning
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.sendto(role.encode(), (HOST, PORT))

    thread_recv = threading.Thread(target=udp_receive, args=(udp_sock,), daemon=False)
    thread_input = threading.Thread(target=udp_input, args=(udp_sock,), daemon=False)
    thread_recv.start()
    thread_input.start()

    thread_recv.join()
    thread_input.join()

### Fonksiyonlar ###


### Main ###
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Kullanım: python Client.py [Doktor|Hasta] [TCP|UDP]")
        sys.exit(1)

    role = sys.argv[1]
    protocol = sys.argv[2]

    role = role.capitalize()
    protocol = protocol.upper()

    if role not in ["Doktor", "Hasta"]:
        print("[HATA] İstemci tipi sadece 'Doktor' veya 'Hasta' olabilir.")
        sys.exit(1)

    if protocol not in ["TCP", "UDP"]:
        print("[HATA] Bağlantı tipi sadece 'TCP' veya 'UDP' olabilir.")
        sys.exit(1)

    if role == "Doktor" and protocol != "TCP":
        print("[HATA] Doktorlar sadece TCP ile bağlanabilir.")
        sys.exit(1)

    if protocol == "TCP":
        sendTCP(role)
    else:
        sendUDP(role)
### Main ###
