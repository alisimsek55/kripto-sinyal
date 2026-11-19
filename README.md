# kripto-sinyal

Yalnız spot, kaldıraçsız, düzenli alım yapan biri için kurala dayalı sinyal ve geri test aracı.
DOGE ve BTC için "fiyat X olursa elindekinin %N'sini sat, Y'ye düşerse nakdinin %M'siyle geri al"
türünde somut seviyeler verir. Seviyelerin arkasında, geçmiş veride dürüstçe test edilmiş kurallar vardır.
Kural düz düzenli alımı geçemiyorsa araç bunu açıkça söyler.

## Kurulum

Python 3.13, `pandas`, `numpy`, `requests` (test için `pytest`). Proje klasöründe:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install pandas numpy requests pytest
.venv\Scripts\python.exe -m kripto_sinyal veri
```

Aşağıdaki `python` komutlarında bu sanal ortamın Python'unu kullan (Windows'ta
`python` yerine `.venv\Scripts\python.exe` yazabilirsin). Depoda örnek geri test
sonuçları bulunur; kendi indirdiğin veriyle yenilemek için `geritest` çalıştır.

## Komutlar

| Komut | Ne yapar |
|---|---|
| `python -m kripto_sinyal veri` | Binance'ten günlük mumları indirir, `veri/` içinde saklar. Sonraki çalıştırmalarda yalnız yeni günleri çeker. |
| `python -m kripto_sinyal geritest` | Parametreleri arar, yıl yıl dürüst test eder, raporu yazar ve `sonuc/parametreler.json` dosyasına kaydeder (birkaç saniye). |
| `python -m kripto_sinyal tavsiye` | Ana coin için kısa özet: bugün ne yapmalı, hangi fiyatta satmalı / geri almalı (aşağıda). |
| `python -m kripto_sinyal takip-baslat` | İlk parametreleri son bitmiş mumda kaydedip ileri takibi başlatır; güncel veri gerekir. |
| `python -m kripto_sinyal karne` | Başlangıç seçimi ve sonraki yıllık seçimlerin sonuçlarını düz alımla karşılaştırır. |
| `python -m kripto_sinyal gecmis` | Gerçek Binance işlemlerini iki varsayımsal sonuçla karşılaştırır. |
| `python -m kripto_sinyal coinler` | Aynı kuralları 11 coinde (DOGE, BTC, ETH, SOL, XRP, ADA, BNB, LTC, LINK, TRX, SHIB) dener, `sonuc/coinler.json` dosyasına yazar. |
| `python -m kripto_sinyal islem ...` | Kendi gerçek işlemini kaydeder (`durum.json`). Geri alım seviyesi senin gerçek son satışına göre hesaplanır. |

`islem` örnekleri:

```powershell
python -m kripto_sinyal islem sat DOGE --fiyat 0.25 --yuzde 20          # elindekinin %20'sini sattım
python -m kripto_sinyal islem al DOGE --fiyat 0.20 --miktar 150          # 150 USDT ile geri aldım
python -m kripto_sinyal islem sat BTC --fiyat 900000 --yuzde 30 --kural uzun
python -m kripto_sinyal islem liste
```

Aylık düzenli alımlarını kaydetmen gerekmez (kaydedersen `--kural duzenli` yaz, seviyeleri etkilemez).

## tavsiye: kısa özet

`python -m kripto_sinyal tavsiye` yalnız ana coini (ayarlardaki `ana_coin`, varsayılan DOGE) kısaca yazar:

- **Başlık:** anlık fiyat; Binance USDT/TRY kuru alınabildiyse TL karşılığı.
- **BUGÜN:** bugün yapılacak tek iş: satış, geri alım ya da "İşlem yok".
  Günlük veri eski, boşluklu veya bozuksa işlem sinyali yerine uyarı yazılır.
- **DİKKAT:** yalnız coinle ya da Binance ile ilgili ciddi bir haber varsa çıkar.
- **KURAL (deneysel ...):** SAT ve GERİ AL satırlarının deneysel bir kural olduğunu ve geçmiş
  testte düz alımın gerisinde mi önünde mi kaldığını söyler.
- **SAT:** gün sonu kapanışı bu fiyatın üstündeyse elindekinin ne kadarını satacağın.
  Altındaki **Hesap** satırı iki ihtimali gösterir: satıp fiyat düşünce geri alırsan coin adedin
  ne kadar artar; fiyat yükselince geri alırsan ne kadar azalır (komisyon ve kayma dahil;
  paranın yalnız bir kısmıyla geri alınıyorsa kalan para nakitte sayılır).
- **GERİ AL:** sattıktan sonra fiyat ne kadar düşerse satış parasıyla geri alacağın.
- **YENİ PARA:** yeni para yatırırken beklemeli mi, hemen mi almalı.
- **FİYAT:** fiyatın 200 günlük ortalamaya uzaklığı (YÜKSEK / ÇOK YÜKSEK uyarısı).
- **30 GÜN:** son 3 yılın 30 günlük fiyat hareketleri son bitmiş kapanışa uygulanırsa fiyatın
  çoğunlukla gittiği aralık (%10 ve %90 dilimleri; yüzdeler şu anki fiyata uzaklık). Tahmin ya da
  olasılık değil, tarihsel bir senaryodur. En az 1125 günlük veri yoksa yazılmaz.
- **SENİN DURUMUN:** `gecmis/` klasöründeki Binance dışa aktarımına göre elindeki coin,
  değeri ve başa baş fiyatın.
- **RİSK:** yalnız elindeki coin biliniyorsa: coin %50 düşerse elindekinin değeri (kur varsa TL,
  yoksa $) ve coinin geçmişte zirvesinden en çok ne kadar düştüğü (günlük kapanışlarla).
- **BTC:** ana coin BTC değilse, Bitcoin'in fiyatı ve piyasa havası tek satırda.
- **Not:** satış kuralının geçmiş testteki sonucu; `sonuc/coinler.json` varsa aynı yöntemin
  kaç coinde düz alımı geçtiği.

Sayılar Türkçe yazılır: ondalık virgül, binlik nokta (ör. `0,0590 $`, `65.034 $`, `5.000 TL`,
`98,3 USDT`). Kur internetten alınamayıp kayıttan geldiyse başlıkta "— eski kur" yazar.

Seçenekler:

```powershell
python -m kripto_sinyal tavsiye --tutar 5000     # 5000 TL kaç USDT ve kaç coin eder
python -m kripto_sinyal tavsiye --coin BTC       # kısa özeti başka coin için yaz
python -m kripto_sinyal tavsiye --ayrinti        # eski tam çıktı: tüm coinler, kanıt, haberler, kur
```

Kur `veri/kur.json` dosyasında saklanır; internet yoksa son kayıtlı kur, o da yoksa TL'siz yazılır.
Günlük sinyal için son kapanış dünün (UTC) kapanışı olmalıdır; daha eski veride `veri`
komutuyla güncelleme istenir. Okunamayan işlem kaydı kişisel sinyal üretimini durdurur.

Testler: `.venv\Scripts\python.exe -m pytest -q` (ağa çıkmaz).

## İşlem geçmişi

Binance'te `Orders > Spot Order > Trade History > Export` yoluyla CSV dosyasını indirip `gecmis/`
klasörüne koy ve `python -m kripto_sinyal gecmis` çalıştır. Rapor, gerçekte kalan coin ve USDT'yi;
aynı para girişleriyle hiç satış yapılmasaydı oluşacak sonucu; aynı toplam para aylara eşit bölünseydi
oluşacak düz aylık alımı karşılaştırır. Aynı rapor `gecmis/rapor.txt` dosyasına da yazılır.
Kur alınabildiyse her sonucun bugünkü kurla TL karşılığı da yazılır (geçmiş alımların o günkü
TL maliyeti değildir).

## İleriye dönük takip

`python -m kripto_sinyal takip-baslat` ilk parametreleri o günkü bitmiş veride dondurur.
Varsayılan başlangıç için tüm coinlerin dünkü kapanışı gerekir; eski önbellek gerçek ileri
takip olarak kaydedilmez. İlk takvim yılında başlangıç seçimi kullanılır. Her yeni takvim
yılında parametreler yalnız önceki yıl sonuna kadarki veriyle yeniden seçilir; portföy durumu
taşınır. Dondurulan, başlangıç seçimi ve bu yıllık seçim yöntemidir; parametreler ömür boyu sabit değildir.
`python -m kripto_sinyal karne` yalnız bu tarihten sonra biten günleri ölçer ve düz aylık alımla karşılaştırır.
Kısa dönem dalgalanmaları yanıltıcı olduğu için hüküm vermeden önce en az 180 gün beklenir.
`takip-baslat --tarih YYYY-AA-GG` yalnız geçmiş veri üzerinde gösterim içindir; gerçek ileri takip değildir.

`karne` ayrıca **30 günlük senaryo karnesi** yazar: takip başlangıcından itibaren 30 günde bir
açılan, üst üste binmeyen dönemlerde, aralık yalnız dönem başına kadarki veriyle hesaplanır ve
dönem sonundaki kapanışın aralıkta kalıp kalmadığı sayılır. Yöntem 19.11.2026'da eklendi ve
donduruldu: ufuk 30 gün, pencere son 1095 günlük 30 günlük getiri (üst üste binen, log getiri),
%10 ve %90 dilimleri, en az 1125 kapanış (`kripto_sinyal/aralik.py`). Bu ayarlar değiştirilmez;
aralığın gerçekten işe yarayıp yaramadığını bu karne gösterir.

## coinler: başka coinlerde aynı test

`python -m kripto_sinyal coinler` Binance'ten (aynı önbellek, `veri/`) ETH, SOL, XRP, ADA, BNB, LTC,
LINK, TRX ve SHIB günlük mumlarını indirir; DOGE ve BTC ile birlikte her coinde `geritest`teki
aynı seçim ve ileri yürüyüş testini çalıştırır. Geçmişi çok kısa olan coin atlanır ve yazılır.
Sonuç `sonuc/coinler.json` dosyasına yazılır (depoda tutulur; kişisel bilgi yoktur):
her coin ve kural için düz aylık alıma göre zincir oranı, her kural için kaç coinde düz alımı
geçtiği ve oranların geometrik ortalaması. `tavsiye` bu dosya varsa son Not satırında kullanır.

## Ayarlar

`ayarlar.json`: aylık tutar (varsayılan 100 USDT), komisyon (%0.1), kayma (%0.05), coinler,
`ana_coin` (kısa özetin coini, varsayılan DOGE).

## Nasıl çalışır

**Model.** Her ayın ilk günü sabit tutar coin alınır. Karşılaştırma ölçütü "düz düzenli alım"dır:
aynı alımlar, hiç satış yok. Strateji aynı aylık alımları yapar, ek olarak kurala göre satar / geri alır.
Bir günün kapanışında çıkan sinyal ertesi günün açılışında uygulanır (geleceğe bakış yok).
Her işlemde komisyon + kayma ödenir. Bugünün bitmemiş mumu testte kullanılmaz.

**Kısa vade kuralı.** N günde en az %X yükseldiyse elindekinin %S'sini sat. Tekrar satış için fiyat
son satışın en az X/2 üstüne çıkmalı (merdiven). Kapanış, son satışın veya son geri alımın
%Y altına inerse kalan nakdin %B'siyle ertesi açılışta geri al; açılış fiyatı değişebilir.
Geri alımdan sonra satış merdiveni sıfırlanır. Satıştan T gün sonra kalan nakit, ilk ay
başından itibaren 3 ayda eşit parçalarla geri alınır (T = "yok" ise süre sınırı yok).

**Uzun vade kuralı.** Fiyat / 200 günlük ortalama oranı U'yu geçerse %SL sat (sonraki satış U×1.25,
U×1.25² ...; oran 1'in altına inince merdiven sıfırlanır). Oran L'nin altındaysa en fazla
30 günde bir nakdin %BL'si ile al. Aynı T kuralı.

**Alım ayarı (satış yok).** Fiyat 200 günlük ortalamaya göre pahalıyken aylık paranın bir bölümü
yedekte tutulur; ucuzken bu yedeğin bir bölümü aylık alıma eklenir. Yedek de portföy değerine katılır.
Her anda alıma ayrılan para ile yedeğin toplamı düz düzenli alımdaki toplam katkıyla aynıdır. Bu,
aynı veride denenen dördüncü kural ailesidir; küçük bir üstünlük tesadüf olabilir.

Kısa ve uzun kural ayrı ayrı ve birlikte test edilir. Her kural yalnız kendi satışından gelen nakdi kullanır.

**En iyi parametre nasıl seçilir.**
- Kaba ızgara: kısa 288, uzun 216 kombinasyon.
- Puan: eğitim sonunda strateji / düz alım oranının logaritması. Her kombinasyon, ızgaradaki komşularıyla birlikte
  ortalanır; tek bir şanslı nokta yerine "geniş iyi bölge" seçilir.
- En iyi komşu ortalamalı puan sıfırdan büyük değilse kural **kapatılır** (düz alım).
- İleri yürüyüş testi: Y yılı için parametre yalnız Y-1 sonuna kadarki veriyle seçilir, Y yılına
  dokunmadan uygulanır. DOGE için 2021'den, BTC için 2019'dan itibaren her yıl.
- Test yılları zincirlenir: ilk yıl düz alımcının o günkü durumuyla başlar, sonraki yıllar durumu
  (coin, nakit, son satış) devralır. "Yıl oranı" o yıl düz alıma göre ne kadar öne / geriye geçildiğidir;
  yıl oranlarının çarpımı zincir sonucudur. Kural kapatıldığında elde kalan nakit, sonraki üç ayın
  ilk mumlarında eşit parçalarla coine geri alınır.
- `tavsiye`deki seviyeler tüm veriyle yapılan seçimden gelir. Yanındaki kanıt sayıları ise bu seçim
  yönteminin görmediği yıllardaki performansıdır (asıl dürüst tahmin budur).

## Çıktıyı okuma

- `x0.85 (%15 geride)`: strateji, aynı dönemde düz düzenli alımın %85'i kadar değer bıraktı.
- Yıl tablosu: her satır, o yıl için yalnız önceki yıllarla seçilmiş parametre ve o yılın sonucu.
  Tek bir yıl (ör. DOGE 2021) sonucu tek başına belirleyebilir; bu yüzden "en iyi yıl çıkarılınca"
  satırı da verilir.
- "Eğitim içi sonuç" iyimserdir, kanıt değildir. Görmediği yıllardaki sonuçla arasındaki fark,
  aşırı uydurmanın büyüklüğünü gösterir.
- HÜKÜM satırı kuralın düz alımı geçip geçmediğini sade biçimde söyler.

## Araştırma sonuçları

- Depoda yeniden üretilebilen testler: kısa ve uzun vadeli satış, bunların birleşimi ve alım ayarı.
  `sonuc/parametreler.json` içindeki 14.11.2026'ya kadar olan veride bu dört ailenin hiçbiri
  DOGE veya BTC'de düz alımı geçmedi.
- `sonuc/coinler.json` (18.11.2026) içindeki 11 coinin kısa satışta 4'ü, uzun satışta 3'ü,
  birleşimde 4'ü, alım ayarında 3'ü düz alımı geçti. Her ailenin geometrik ortalama oranı 1'in altında.
- Korku-Açgözlülük endeksi yalnız ruh hali olarak gösterilir; endeksten al/sat sinyali üretilmez.
- 30 günlük aralıkta %10 ve %90 dilimleri kullanılması, gelecekte %80 kapsama garantisi vermez.
  Depodaki JSON sonuçları geçmiş yıllar için bir kapsama ölçümü içermiyor; ileri kapsama `karne` ile izlenir.
- Asıl sınav ileri takiptir (`karne`): başlangıç seçimi, yıllık yeniden seçim yöntemi ve aralık
  yöntemi belirlenir; dönemler sonraki fiyatlarla ölçülür. `--tarih` ile başlatılanlar geçmiş gösterimidir.

## Dürüst sınırlar

- Araç fiyatın yönünü tahmin edemez. Yalnız geçmişte işe yarayıp yaramadığını ölçer.
- Geçmiş gelecek değildir. Kripto piyasası değişir.
- Büyük yükseliş olayı çok azdır (DOGE'de esasen 2021). Sonuçlar birkaç olaya bağlıdır.
- Bu tür "yükselişte sat" kurallarının ana riski: satarsın, fiyat geri gelmez. Geçmiş testlerde
  çoğu zaman düz düzenli alım daha iyi çıktı; araç bunu saklamaz.
- Vergi, transfer ücreti, borsa riski hesaba katılmaz.
- Bu araç yatırım tavsiyesi değildir.

## Yayın öncesi kontrol

Depo herkese açık olduğu için push'tan önce `araclar/yayin_kontrol.py` kişisel bilgi arar.
Bulursa push'u durdurur ve yeri (`dosya:satır`, commit) ile türünü yazar; değerin kendisini
yazmaz, yalnız maskeli gösterir (ör. `43***`).

Engellenenler:
- Özel dosyalar: `gecmis/` klasörü, `durum.json`, `veri/kur.json`, `takip/karne.json`,
  Binance işlem CSV'leri, `.env`, özel anahtar dosyaları.
- `gecmis/` içindeki gerçek CSV'lerden çalışma anında hesaplanan değerler: emir numaraları,
  işlem miktarları, elde tutulan coin, giren para, cep, başa baş fiyatı.
- Portföy değerine (son 120 günün kapanışlarıyla, USDT ve TL) ±%1,5 yakın 1000 ve üstü sayılar.
- API anahtarı, şifre, belirteç ve özel anahtar kalıpları.

Hassas değerler yalnız bellekte tutulur, hiçbir dosyaya yazılmaz. `gecmis/` boşsa bakiye ve
portföy kontrolleri atlanır. CSV varsa fakat defter hesaplanamıyorsa kontrol başarısız olur (çıkış 2).
UTF-16/UTF-32 BOM'lu Windows metinleri de taranır; özel dosya yollarında büyük/küçük harf ayrılmaz.
Bu tarama sezgiseldir; sayısal benzerlikler örneklerde ve testlerde yanlış alarm verebilir.

```
python araclar/yayin_kontrol.py --agac              # izlenen dosyalar
python araclar/yayin_kontrol.py --commitler HEAD    # tüm yerel geçmiş
```

Push kancası bir kez `python araclar/kancayi_kur.py` ile kurulur; sonra her `git push`
yalnız gönderilecek commitleri tarar.
