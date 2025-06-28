# Socket Programlama ile Hastane Doktor Randevu Uygulaması

Bu proje, Python kullanarak socket programlama (TCP/UDP) yeteneklerinizi geliştirmek amacıyla hazırlanmış basit bir hastane doktor randevu uygulamasıdır. Gerçek bir sağlık otomasyonu yerine, istemci-sunucu iletişimi, çoklu thread kullanımı ve temel randevu akışının örneklendiği bir eğitim projesidir.

## Özellikler

* **Doktor/Hasta Rolleri**: İstemci, "Doktor" veya "Hasta" rolüyle başlatılabilir.
* **TCP ve UDP Desteği**: Hem TCP hem de UDP protokolleriyle mesajlaşma.
* **Thread Tabanlı İletişim**: Hem sunucu hem istemci tarafında eşzamanlı mesaj alıp göndermek için thread kullanımı.
* **Ön Tanımlı Randevular**: `randevu.txt` dosyasından doktor-hasta eşleştirmeleri yüklenir.
* **Basit Randevu Akışı**: Doktorlar "Hasta Kabul" komutuyla sıradaki hastalarını çağırır, onay/ret durumları işlenir.

## Gereksinimler

* Python 3.6 veya üzeri
* Standart kütüphaneler: `socket`, `threading`, `time`, `sys`

## Çalıştırma

### Sunucu

```bash
python Server.py
```

* Sunucu, `randevu.txt` dosyasını okuyarak randevu listesini oluşturur.
* Hem TCP hem de UDP bağlantılarını dinler.

### İstemci

```bash
python Client.py [Doktor|Hasta] [TCP|UDP]
```

* Örnek: `python Client.py Doktor TCP`
* Hasta için hem TCP hem UDP kullanılabilir; doktorlar yalnızca TCP üzerinden bağlanır.
* `XXX` mesajıyla bağlantıyı sonlandırabilirsiniz.

## Dosya Yapısı

```plaintext
socket-hastane-randevu/
├── Server.py        # Sunucu uygulaması
├── Client.py        # İstemci uygulaması
├── randevu.txt      # Doktor-hasta randevu tanımları
└── README.md        # Proje dokümantasyonu
```

## Randevu Dosyası Formatı

Her satır şu formatta olmalıdır:

```
DoktorAdı;Hasta1,Hasta2,Hasta3
```

Örnek:

```
Doktor1;Hasta1,Hasta3
Doktor2;Hasta2
```
