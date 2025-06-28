# BARAN KANAT - 22100011013


# ------------------------------------------------------------
# HASTANE RANDEVU SISTEMI - DETAYLI ACIKLAMA
#
# 1. SUNUCU BASLANGICI:
#    - HOST ve PORT ayarlanir.
#    - Randevu dosyasi filetoDict ile okunur ve Randevular sozlugune aktarilir.
#    - monitorAppointments thread'i calismaya baslar:
#       * 2 saniyede bir Randevular, currentRandevu ve randevusuzHastalar kontrol edilir.
#       * Tum randevular ve bekleyen hastalar bitmis ise,
#         tum doktor baglantilarina kapanis mesajlari gonderilip listeler sifirlanir.
#
# 2. ISTEMCI KABULU:
#    - handleTCP thread'i:
#       * Tum yeni TCP baglantilari server_socket.accept ile yakalanir.
#       * Her baglanti newClient(conn,addr) fonksiyonuna gonderilir.
#    - newClient fonksiyonu:
#       * Rol (Doktor/Hasta) ilk mesajda tespit edilir.
#       * Doktor: DoktorConnList ve DoktorClientList sozluklerine eklenir.
#       * Hasta TCP: HastaConnList, HastaClientList ve clientList'e eklenir.
#       * Hasta UDP: handleUDP1 icindeki ClientUDP ile HastaUDPList, HastaClientList, clientList guncellenir.
#       * Yeni hasta kayit edilince notifyDoctors ile doktorlara bilgi gonderilir.
#
# 3. MESAJ YONETIMI:
#    - GecmisMesajlar sozlugune port bazli tum gelen ve giden mesajlar eklenir.
#    - 'XXX' komutu alindiginda istemci baglantisi kapatilir ve sozluklerden silinir.
#
# 4. RANDEVU ISLEMLERI:
#    4.1 Randevu Okuma:
#         - filetoDict('randevu.txt') ile Randevular sozlugune { 'Doktor1': [...], ... } yuklenir.
#
#    4.2 Hasta Kabul Asamasi:
#         - Doktor 'Hasta Kabul' yazinca:
#           1) accept_lock kilidi alinir, diger doktorlar bekletilir.
#           2) currentRandevu varsa separatedPatient ile sonlandirilir.
#           3) ListPatients(portDoctor) ile doktorun Randevular listesi alinir.
#           4) Liste dolu ise acceptPatients(patients,portDoctor) cagrilir.
#           5) Liste bos ise:
#              a) doctorMostPatients() ile en cok hastasi olan doktor bulunur.
#              b) findPatient(bussyDoctor) ile o doktorun ilk hastasi secilir.
#              c) Secilen hasta acceptPatients ile isleme dahil edilir.
#              d) Hic randevu kalmadiysa randevusuzHastalar kullanilir.
#
#    4.3 Onay Sureci (acceptPatients):
#         - Her hasta icin:
#           * TCP/UDP ayrimina gore mesaj gonderilir.
#           * 10 saniye boyunca accept_lock icerisinde beklenir.
#           * GecmisMesajlar[port] listesinde 'evet' kontrol edilir:
#              - Varsa Acceptance(portHasta,portDoktor):
#                  . currentRandevu[Doktor] = Hasta
#                  . Randevular sozlugunden Hasta silinir.
#                  . Doktor ve Hasta bilgilendirilir.
#              - Yoksa cancelAppointment(portHasta,portDoktor):
#                  . Randevu iptal edilir, randevusuzHastalar listesine eklenir.
#                  . Doktor ve Hasta bilgilendirilir.
#
#    4.4 Randevu Tamamlama (separatedPatient):
#         - currentRandevu[Doktor] icindeki hasta TCP/UDP baglantisi kapatilir.
#         - Ilgili tum kayitlar (ConnList, GecmisMesajlar, vs.) silinir.
#         - Doktor bir sonraki hastaya gecis yapabilir.
#
# 5. VERI YAPILARI GUNCELLEME:
#    - clientList          : tum aktif kullanicilar (port->isim)
#    - DoktorConnList      : doktor portu -> TCP socket
#    - DoktorClientList    : doktor portu -> DoktorN
#    - HastaConnList       : hasta portu -> TCP socket (None ise UDP)
#    - HastaUDPList        : UDP hastalar icin adres bilgisi
#    - HastaClientList     : hasta portu -> HastaM
#    - Randevular          : doktorlara ozel randevulu hasta listeleri
#    - randevusuzHastalar  : siradaki randevusuz hastalar
#    - currentRandevu      : aktif muayene edilen doktor->hasta eslesmeleri
#    - GecmisMesajlar      : port bazli mesaj kayitlari (evet onayi icin)
#
# ------------------------------------------------------------


### Kutuphaneler ###
import socket
import threading
import time
### Kutuphaneler ###

### Sunucu Bilgileri ###
HOST = '127.0.0.1'
PORT = 12345
BUFFER_SIZE = 1024
### Sunucu Bilgileri ###

### Degsikenler ###
#hasta kabul sirasinda gecislerde diger threadlerin calismasi engellemek icin
accept_lock = threading.Lock()

#udp baglantisi icin
udp_socket = None

clientList = {}

# Doktorlar listesi
DoktorConnList = {}
DoktorClientList = {}
countDoktor = 0 # doktor sayisi

#Hastalar listesi
HastaUDPList = {}
HastaConnList = {}
HastaClientList = {}
countHasta = 0 # hasta sayisi

#gecmis mesajlari portlara gore tutan sozluk
GecmisMesajlar = {}

#dosyadaki randevulari tutan sozluk
# örnk: {'Doktor1': ['Hasta1', 'Hasta3'], 'Doktor2': ['Hasta2'], 'Doktor3': []}
Randevular = {}
# örnk: ['Hasta3', 'Hasta7', 'Hasta5']
randevusuzHastalar = []

#hangi doktorun hangi hastaya o an baktigini tutan liste
currentRandevu = {}
### Degiskenler ###

### Fonksiyonlar ###
#Randevulu hastalarin kalmadigi durumda tum doktorlara haber verilsin ve doktorlarin baglantisi kesilmesi icin mesaj gonderilsin.
def monitorAppointments():
    global Randevular, currentRandevu, DoktorConnList, udp_socket

    while True:
        allEmpty = True

        # Burada kilidi almaya çalışacak; eğer bir doktor acceptPatients ile kilidi tutuyorsa,
        # bu satır bloklanır ve monitor thread bekler
        with accept_lock:

            for doktor, hastaListesi in Randevular.items():
                if len(hastaListesi) != 0:
                    allEmpty = False
                    break

            if allEmpty and not currentRandevu and not randevusuzHastalar:
                print("[HASTAHANE] Bekleyen hasta kalmadı. Tüm doktor oturumları kapatılıyor...")

                for port, conn in list(DoktorConnList.items()):
                    try:
                        conn.sendall("[HASTAHANE] Bekleyen hasta bulunmamaktadır. Oturumunuz kapatılıyor.".encode())
                        #conn.shutdown(socket.SHUT_RDWR)
                        #conn.close()

                        del DoktorConnList[port]
                        del DoktorClientList[port]
                        del clientList[port]

                    except Exception as e:
                        print(f"[monitorAppointments] HATA, Doktor port {port} kapatılamadı: {e}")

                break  # İşlem tamamlandıktan sonra thread sonlansın

        time.sleep(2)  # 3 saniyede bir kontrol et


#En çok hastasi bulunan doktorun portunu donduren fonksiyon
def doctorMostPatients():
    global Randevular

    if not Randevular or not DoktorClientList:
        return None

    maxPatCount = 0
    bussyDoctor = None

    for doctor, patList in Randevular.items():
        patCount = len(patList)

        if patCount > maxPatCount:
            maxPatCount = patCount
            bussyDoctor = doctor

    # Eğer en yoğun doktorun hastası yoksa None döndür
    if maxPatCount == 0:
        return None

    return bussyDoctor

#en cok hastasi olan doktoru alir ve ilk hastasini dondurur.
def findPatient(nameDoctor):
    global Randevular

    # Doktorun hasta listesine eriş
    patientList = Randevular.get(nameDoctor, [])

    # Eğer listede hasta yoksa None döndür
    if not patientList:
        return None

    # İlk hastayı listeden çıkar ve döndür
    namePatient = patientList.pop(0)

    return namePatient

#doktorun yeni bir hasta cagirdiginda aktif hastasinin (CurrentRandevu) kismindan hastayi cikaran ve sistemden atan fonk.
def separatedPatient(portDoctor):
    global udp_socket, currentRandevu, HastaUDPList

    nameDoktor = DoktorClientList.get(portDoctor)

    # Eğer doktorun aktif hastası yoksa
    if nameDoktor not in currentRandevu:
        print(f"[HASTAHANE] {nameDoktor} şu anda aktif bir hasta ile ilgilenmiyor.")
        return

    nameHasta = currentRandevu[nameDoktor]

    # Hasta portunu bul (HastaClientList sözlüğünde isimden porta ulaşacağız)
    portHasta = None
    for port, hastaIsmi in HastaClientList.items():
        if hastaIsmi == nameHasta:
            portHasta = port
            break

    if portHasta is not None:
        try:

            #hasta UDP hasta ise
            if HastaConnList[portHasta] == None:

                hastaName = clientList[portHasta]
                addr = HastaUDPList[portHasta]

                udp_socket.sendto(f"Randevunuz tamamlandı, sistemden çıkış yapılıyor.".encode(), addr)
                udp_socket.sendto(f"Geçmiş Olsun".encode(), addr)

                del HastaUDPList[portHasta]
                del HastaConnList[portHasta]
                del HastaClientList[portHasta]
                del GecmisMesajlar[portHasta]

                print(f"[HASTAHANE] {hastaName}, Ayrıldı.")

            #Hasta TCP hasta ise
            else:
                # Hastaya bilgi gönder
                HastaConnList[portHasta].sendall("Randevunuz tamamlandı, sistemden çıkış yapılıyor.".encode())

                conn = HastaConnList[portHasta]
                try:
                    # Hastaya sadece bir çıkış komutu gönderiyoruz
                    conn.sendall("Geçmiş Olsun".encode())
                except Exception:
                    pass

                # Hastayı sistemden sil
                del HastaConnList[portHasta]
                del HastaClientList[portHasta]
                del GecmisMesajlar[portHasta]

                print(f"[HASTAHANE] {nameHasta}, Ayrıldı.")

        except Exception as e:
            print(f"[separatedPatient] HATA, {nameHasta} sistemden çıkarılırken hata oluştu: {e}")

    else:
        print(f"[HASTAHANE] {nameHasta} sistemde bulunamadı!")

    # Doktorun aktif hastasını currentRandevu listesinden sil
    del currentRandevu[nameDoktor]

    #print(f"[HASTAHANE] {nameDoktor} artık yeni hasta çağırabilir.")


#randevusunu kabul etmeyen hasta randevusunu silen ve randevusuzHastalar listesine ekleyen fonksiyon
def cancelAppointment(portHasta, portDoktor):
    global randevusuzHastalar, udp_socket

    nameDoktor = DoktorClientList.get(portDoktor)
    nameHasta = HastaClientList.get(portHasta)

    # Doktorun randevu listesini al
    doktorHastalar = Randevular.get(nameDoktor, [])

    # Eğer hasta listede varsa
    if nameHasta in doktorHastalar:
        doktorHastalar.remove(nameHasta)  # Hastayı listeden çıkar
        randevusuzHastalar.append(nameHasta)  # Randevusuz hastalar listesine ekle

        print(f"[HASTAHANE] {nameHasta}, {nameDoktor} randevusundan çıkarıldı ve randevusuzlar listesine eklendi.")

        ###UDP HASTA (START) ###
        if HastaConnList[portHasta] == None:
            addr = HastaUDPList[portHasta]

            udp_socket.sendto("[HASTAHANE] randevunu kabul etmedigin icin randevu hakkını kaybettin.".encode(), addr)
        ###UDP HASTA (END) ###

        ###TCP HASTA (START) ###
        else:
            # hastaya randevunun iptal edildigi hakkinda bilgi ver.
            HastaConnList[portHasta].sendall(
                "[HASTAHANE] randevunu kabul etmedigin icin randevu hakkını kaybettin.".encode())
        ###TCP HASTA (END) ###


        # Doktora bilgi ver
        DoktorConnList[portDoktor].sendall(f"{nameHasta} randevusuna gelmediği için randevusu iptal edildi.".encode())

    #hasta randevusuzlar listesindeyse
    elif nameHasta in randevusuzHastalar:
        randevusuzHastalar.remove(nameHasta)

        ###UDP HASTA (START) ###
        if HastaConnList[portHasta] == None:
            addr = HastaUDPList[portHasta]

            udp_socket.sendto("[HASTAHANE] randevuyu kabul etmedigin icin tedavi hakkini kaybettin".encode(), addr)
        ###UDP HASTA (END) ###

        ###TCP HASTA (START) ###
        else:
            # hastaya randevunun iptal edildigi hakkinda bilgi ver.
            HastaConnList[portHasta].sendall(
                "[HASTAHANE] randevuyu ikinci kere kabul etmedigin icin tedavi hakkini kaybettin.".encode())
        ###TCP HASTA (END) ###

        # Doktora bilgi ver
        DoktorConnList[portDoktor].sendall(
            f"{nameHasta} tekrar muayeneye gelmediği için tedavi hakkı iptal edildi.".encode())

    else:
        print(f"[HASTAHANE] {nameHasta}, {nameDoktor} randevu listesinde bulunamadı.")

#randevulari sozluge kaydeden fonksiyon
def filetoDict(dosyaAdi):
    randevular = {}

    try:
        with open(dosyaAdi, "r", encoding="utf-8") as dosya:
            for satir in dosya:
                satir = satir.strip()  # Satırdaki boşlukları temizle

                if satir == "":
                    continue  # Boş satırı geç

                parcalar = satir.split(";")  # Doktor ve hastaları ayır

                doktor = parcalar[0]  # Doktor ismi
                if len(parcalar) > 1 and parcalar[1] != "":
                    hastalar = parcalar[1].split(",")  # Hastaları liste yap
                else:
                    hastalar = []  # Eğer hasta yoksa boş liste

                randevular[doktor] = hastalar  # Sözlüğe ekle

    except FileNotFoundError:
        print(f"[filetoDict] Hata, {dosyaAdi} bulunamadı!")

    return randevular

#hasta randevuyu kabul etti fonksiyonu
# İlgili hasta doktoru kabul ettiğinde bir fonksiyon çağırılmalı ve bu fonksiyon ile hem hasta hem de doktor ekranında
#   “HastaX DoktorY randevusunu kabul etti” şeklinde bilgi gösterilmelidir
def Acceptance(portHasta = "", portDoktor = ""):
    global currentRandevu, udp_socket

    nameDoktor = DoktorClientList.get(portDoktor)
    nameHasta = HastaClientList.get(portHasta)

    msg = f"[HASTAHANE] {nameHasta}, {nameDoktor} randevusunu kabul etti."
    GecmisMesajlar[portHasta] = ['evetX' if msg == 'evet' else msg for msg in GecmisMesajlar[portHasta]]

    ### HASTA UDP (START) ###
    if HastaConnList[portHasta] == None:

        addr = HastaUDPList[portHasta]
        udp_socket.sendto(msg.encode(), addr)
    ### HASTA UDP (END) ###

    ### HASTA TCP (START) ###
    else:
        HastaConnList[portHasta].sendall(msg.encode())
    ### HASTA TCP (END) ###


    DoktorConnList[portDoktor].sendall(msg.encode())
    currentRandevu[nameDoktor] = nameHasta

    #Onayi kabul eden hasta randevular listesinden silinsin.
    for doktor, hastaListesi in Randevular.items():
        if nameHasta in hastaListesi:
            hastaListesi.remove(nameHasta)
            #print(f"[HASTAHANE] {nameHasta}, {doktor} randevu listesinden silindi.")
            break

    #randevusuz hasta ise randevusuz hastalar bolumunden silinsin
    if nameHasta in randevusuzHastalar:
        randevusuzHastalar.remove(nameHasta)


    #print(f"Doktorun aktif randevusu: {currentRandevu}")


def NonAcceptance(portHasta = "", portDoktor = ""):
    nameDoktor = DoktorClientList.get(portDoktor)
    nameHasta = HastaClientList.get(portHasta)

    msg = f"{nameHasta}, {nameDoktor} randevusunu kabul etmedi.\nVarsa sonraki hastaye geçilecektir."
    DoktorConnList[portDoktor].sendall(msg.encode())

def acceptPatients(listPat=[], portDoctor=""):
    global HastaClientList, DoktorClientList, udp_socket, accept_lock
    nameDoktor = DoktorClientList.get(portDoctor)

    with accept_lock:
        # Eğer doktorun aktif hastası varsa önce sistemden çıkar
        if nameDoktor in currentRandevu:
            separatedPatient(portDoctor)

        for port, hasta in HastaClientList.items():
            if hasta in listPat:

                msgRandevu = f"[HASTAHANE] {hasta} -> {nameDoktor}, randevusu var."
                msgRandevuHasta = msgRandevu + " Kabul için 'evet' yaz."
                print(msgRandevu) #sunucuda gorulecek mesaj


                ### UDP HASTA (START) ###
                if HastaConnList[port] == None:

                    addr = HastaUDPList[port]
                    udp_socket.sendto(msgRandevuHasta.encode(), addr)
                    time.sleep(10)  # Cevap suresi icin 10 saniye bekle.

                    #Randevuyu onaylarsa
                    if 'evet' in GecmisMesajlar[port]:
                        # hem hastaya hem de doktora randevu onaylandi mesaji gonderilecek.
                        Acceptance(port, portDoctor)
                        return

                    #Randevuyu onaylamazsa
                    else:
                        # sadece doktora randevu onaylanmadi mesaji gidecek.
                        NonAcceptance(port, portDoctor)

                        # randevusu onaylamayan hastanin randevusunu iptal eden fonksiyon
                        cancelAppointment(port, portDoctor)

                        print(f"[HASTAHANE] {nameDoktor}, varsa bir sonraki hastaya geçilecektir.")

                ### UDP HASTA (END) ###

                ### TCP HASTA (START) ###
                else:
                    HastaConnList[port].sendall(msgRandevuHasta.encode())
                    time.sleep(10)  # Cevap suresi icin 10 saniye bekle.

                    # randevuyu onaylarsa
                    if 'evet' in GecmisMesajlar[port]:
                        # hem hastaya hem de doktora randevu onaylandi mesaji gonderilecek.
                        Acceptance(port, portDoctor)
                        return

                    # RANDEVU ONAYLANMAZSA
                    else:
                        # sadece doktora randevu onaylanmadi mesaji gidecek.
                        NonAcceptance(port, portDoctor)

                        # randevusu onaylamayan hastanin randevusunu iptal eden fonksiyon
                        cancelAppointment(port, portDoctor)

                        print(f"[HASTAHANE] {nameDoktor}, varsa bir sonraki hastaya geçilecektir.")
                ### TCP HASTA (END) ###




# Doktorun randevulu hastalarini listeler
def ListPatients(portDoctor=""):
    global DoktorClientList
    nameDoktor = DoktorClientList.get(portDoctor)

    #print(f"doktorun randevulu hasta listesi: {Randevular.get(nameDoktor, [])}")

    return Randevular.get(nameDoktor, [])

#doktorlara hasta bilgisi veren fonksiyon
def notifyDoctors(hasta):
    for port, doktor in DoktorClientList.items():
        try:
            DoktorConnList[port].sendall(f"[HASTAHANE] Yeni hasta ({hasta}) sisteme giriş yaptı.".encode())
        except:
            print(f"[HASTAHANE] {doktor} bilgilendirilemedi.")

#sozlukte karsilik gelen ismi dondurur.
def Person(port):
    global clientList
    return clientList[port]

#doktorun/Hastanın olup olmadigini kontrol eden fonksiyon
def isPerson(list):
    if len(list) == 0:
        return False
    return True

def newClient(conn, addr):
    global clientList, countDoktor, countHasta, GecmisMesajlar, currentRandevu
    role = conn.recv(BUFFER_SIZE)

    port = addr[1]
    GecmisMesajlar[port] = []

    # Gelen doktorsa
    if role.decode() == 'Doktor':

        countDoktor = countDoktor + 1
        DoktorConnList[addr[1]] = conn # burada doktorlarin conn nesnesini tutuluyor
        DoktorClientList[addr[1]] = 'Doktor' + str(countDoktor)
        clientList[addr[1]] = 'Doktor' + str(countDoktor)

    #gelen hastaysa
    elif role.decode() == 'Hasta':

        #sistemde doktor yoksa
        if isPerson(DoktorClientList) == False:
            print("[HASTAHANE] Sistemde aktif doktor bulunmadığı için gelen hasta bağlantısı reddedildi.")
            conn.sendall("[HASTAHANE] Sistemde şu anda doktor bulunmamaktadır. Lütfen daha sonra tekrar deneyiniz.".encode())
            conn.close()
            return

        #sistemde doktor varsa
        else:

            countHasta = countHasta + 1
            hasta = 'Hasta' + str(countHasta)
            HastaConnList[addr[1]] = conn
            HastaClientList[addr[1]] = hasta
            clientList[addr[1]] = hasta

            conn.sendall(f"[HASTAHANE] Hoş geldiniz, {hasta}!".encode())
            print(f"[HASTAHANE] Yeni hasta ({hasta}) sisteme giriş yaptı.")

            # Doktorları bilgilendir
            notifyDoctors(hasta)

            # yeni gelen hasta randevulu degilse randevusuz hastalar listesine eklenmeli.
            in_randevular = any(hasta in hastaList for hastaList in Randevular.values())
            if not in_randevular:
                randevusuzHastalar.append(hasta)
                print(f"[HASTAHANE] {hasta}, randevusuz hasta olarak kaydedildi.")

    #konusmanin sureki olabilmesi icin
    while True:
        try:
            data = conn.recv(BUFFER_SIZE)
            if not data:
                break

            text = data.decode().strip()
            GecmisMesajlar[port].append(text)

            #doktorlarin hasta kabul etmeye baslarsa
            if data.decode() == 'Hasta Kabul' and role.decode() == 'Doktor':
                patients = ListPatients(addr[1])
                if not patients:
                    nameDoktor = DoktorClientList.get(addr[1])

                    # Eğer doktorun aktif hastası varsa önce sistemden çıkar
                    if nameDoktor in currentRandevu:
                        separatedPatient(addr[1])

                    ######## 5.MADDE ########
                    #Doktora mesaj gonderme
                    conn.sendall("[HASTAHANE] Aktif randevun yok, varsa farklı bir doktor'un hastası cağrıldı.".encode())
                    print(f"[HASTAHANE] {nameDoktor}, başka bir doktor'un hastasını çağıyor...")

                    bussyDoctor = doctorMostPatients()

                    if not bussyDoctor:
                        conn.sendall("[HASTAHANE] Hiçbir doktorun aktif randevusu bulunmamaktadır.".encode())
                        print("[HASTAHANE] Tüm doktorların randevuları bitti.")

                        if len(randevusuzHastalar) > 0:
                            conn.sendall(f"[HASTAHANE] Randevusuz hasta bulundu.\n"
                                         f"Kalan randevusuz hasta sayısı: {len(randevusuzHastalar) - 1}".encode())
                            #print(f"{randevusuzHastalar}")

                            # İlk randevusuz hastayı çağırmak için liste oluştur
                            nameHasta = randevusuzHastalar[0]
                            acceptPatients([nameHasta], addr[1])

                        else:
                            print("[HASTAHANE] Bütün hastalar bitti.")

                        #conn.close()
                    else:
                        # Sadece tek bir hasta al
                        namePatient = findPatient(bussyDoctor)

                        if not namePatient:
                            conn.sendall("[HASTAHANE] Aktif bir randevu bulunamadı.".encode())
                            print(f"[HASTAHANE] {nameDoktor} için uygun bir randevu bulunamadi.")
                        else:
                            conn.sendall(f"[HASTAHANE] {namePatient}, hastası çağrılıyor".encode())

                            # Tek hastayı listeye çevirerek acceptPatients'e gönder
                            acceptPatients([namePatient], addr[1])

                    ######## 5.MADDE ########


                else:
                    acceptPatients(patients, addr[1])


            #kullanici cikis verirse
            elif data.decode() == 'XXX':
                print(f"[HASTAHANE] {Person(addr[1])}, çıkış yaptı!\n")

                #print(f"Randevusuzlar: {randevusuzHastalar}")
                #print(f"Kisiler: {clientList}")
                #print(f"Doktorlar: {DoktorClientList}")
                #print(f"Hastalar: {HastaClientList}")

                #listede kullanici varsa kullaniciyi sil
                if addr[1] in clientList:
                    pass

                if addr[1] in DoktorClientList:
                    del DoktorClientList[addr[1]]

                if addr[1] in HastaClientList:
                    del HastaClientList[addr[1]]


                conn.close()
                return

            # Eğer mesajda [HASTAHANE] geçiyorsa yazdır
            decoded_message = data.decode().strip()
            if "[HASTAHANE]" in decoded_message:
                print(f"[{Person(addr[1])}]: {decoded_message}")

        except Exception as e:
            print(f"[newClient] Hata oluştu. {addr}, istemcisi sunucudan atildi. {e}")
            break


def handleTCP():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))

    print("\n#==============================#")
    print("   HASTANE RANDEVU SUNUCUSU  ")
    print("#==============================#\n")

    server_socket.listen()
    # print(f"[TCP] Dinleniyor: {HOST}:{PORT}")

    try:
        while True:
            conn, addr = server_socket.accept()
            thread = threading.Thread(target=newClient, args=(conn, addr))
            thread.start()

            # conn.close()

    except:
        print('[handleTCP] Hata meydana geldi.')


#---- UDP Fonksiyonlari ----#
def ClientUDP(addr, message="alinamadi", udp_socket = None):
    global clientList, HastaUDPList, HastaConnList, HastaClientList, countHasta, DoktorClientList, GecmisMesajlar

    # Conn nesnesine sahip olmadigi icin (UDP), iletisimi her seferinde IP ve PORT araciligiyle yapilmalidir.
    ip = addr[0]
    port = addr[1]

    try:

        ###### YENI BIR HASTA GELDIYSE (START) #####
        if port not in clientList:
            # Hasta kayit edilmeli
            countHasta = countHasta + 1
            hasta = 'Hasta' + str(countHasta)
            HastaConnList[port] = None
            HastaClientList[port] = hasta
            clientList[port] = hasta
            HastaUDPList[port] = addr
            GecmisMesajlar[port] = []

            #hoşgeldin Mesajı
            udp_socket.sendto(f"[HASTAHANE] Hoş geldiniz, {hasta}!".encode(), addr)
            print(f"[HASTAHANE] Yeni hasta ({hasta}) sisteme giriş yaptı.")

            #doktorlara bildirim gonder
            notifyDoctors(hasta)

            #yeni gelen hasta randevulu degilse randevusuz hastalar listesine eklenmeli.
            in_randevular = any(hasta in hastaList for hastaList in Randevular.values())
            if not in_randevular:
                randevusuzHastalar.append(hasta)
                print(f"[HASTAHANE] {hasta}, randevusuz hasta olarak kaydedildi.")
        ###### YENI BIR HASTA GELDIYSE (END) #####

        ##### GELEN HASTA SISTEMDE VAR ISE (START) #####
        else:
            nameHasta = clientList[port]
            GecmisMesajlar[port].append(message)

            ## XXX ile cikis yaptigini belirtir.
            if message == "XXX":
                pass
                #print(f"Kisiler: {clientList}")
                #print(f"Doktorlar: {DoktorClientList}")
                #print(f"Hastalar: {HastaClientList}")
                #print(f"UDPHastalar: {HastaUDPList}")
                #print(f"ConnHastalar: {HastaConnList}")
                #print(f"Randevusuzlar: {randevusuzHastalar}")

            else:
                #hasta udp'in mesajini serverda yazdir.
                if "[HASTAHANE]" in message:
                    print(f"[{nameHasta}]: {message}")


        ##### GELEN HASTA SISTEMDE VAR ISE (END) #####

    except Exception as e:
        pass
        #print(f"[ClientUDP] Hata: {e}")



def handleUDP1():
    global udp_socket, clientList, DoktorClientList

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((HOST, PORT))

    while True:
        try:
            # Baglantiyi ve mesaji al.
            data, addr = udp_socket.recvfrom(BUFFER_SIZE)
            message = data.decode().strip()

            #Sistemde doktor var mi? Kontrol
            if len(DoktorClientList) <= 0:
                print("[HASTAHANE] Sistemde aktif doktor bulunmadığı için gelen hasta bağlantısı reddedildi.")
                udp_socket.sendto(f"[HASTAHANE] Sistemde şu anda doktor bulunmamaktadır. Lütfen daha sonra tekrar deneyiniz.".encode(), addr)


            # UDP Kullanici islemleri
            ClientUDP(addr, message, udp_socket)


        except Exception as e:
            print(f"[handleUDP1] Hata: {e}")

def handleUDP():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind((HOST, PORT))

    print(f"[UDP] Sunucu {HOST}:{PORT} adresinde dinleniyor...")

    while True:
        try:
            data, addr = udp_socket.recvfrom(BUFFER_SIZE)
            message = data.decode().strip()

            port = addr[1]

            if port not in clientList:
                role = message
                if role == "Hasta":
                    clientList[port] = f"Hasta_UDP_{port}"
                    print(f"[HASTANE][UDP] Yeni UDP hasta ({clientList[port]}) sisteme giriş yaptı.")
                    udp_socket.sendto(f"[HASTAHANE] Hoş geldiniz, {clientList[port]}!".encode(), addr)
                else:
                    udp_socket.sendto("[HASTAHANE] UDP ile sadece hastalar bağlanabilir.".encode(), addr)
            else:
                # Hasta mesaj gönderdiğinde yapılacak işlemler
                if message == "XXX":
                    print(f"[HASTANE][UDP] {clientList[port]} çıkış yaptı.")
                    del clientList[port]
                else:
                    print(f"[{clientList[port]}]: {message}")

        except Exception as e:
            print(f"[handleUDP] Hata: {e}")


### Fonksiyonlar ###

### Main ###
# Randevulari sozluge kaydet
Randevular = filetoDict("22100011013_randevu.txt")

#Aktif hasta yoksa (Sadece 'Randevular' ve 'CurrentRandevu' listesi için) doktorlari sistemden ayir.
# Randevu kontrol thread'ini başlat
monitor_thread = threading.Thread(target=monitorAppointments, daemon=True)
monitor_thread.start()

# TCP ve UDP paralel baslat
tcp_thread = threading.Thread(target=handleTCP)
udp_thread = threading.Thread(target=handleUDP1)

tcp_thread.start()
udp_thread.start()

tcp_thread.join()
udp_thread.join()
### Main ###
