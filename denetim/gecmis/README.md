# gecmis denetim betikleri

Bu betikler, `gecmis` komutunu denetlemek için bağımsız bir denetçi tarafından 2026-11-15'te
80be3ce commit'ine karşı yazıldı. G1–G4 denetimleri geçti. G5, alımlarda iki ücret hatası buldu
(üçüncü varlıkla ve kotasyon varlığıyla ödenen alım ücretleri); bu hatalar sonradan düzeltildi,
bu yüzden g5 hâlâ FAIL yazar ve g1 hâlâ düzeltme öncesi ücret formülünü kullanır.
Betikler kanıt olarak saklanır, test takımının parçası değildir; veriyi çalışırken `gecmis/`
klasöründen okur, içlerinde kişisel sayı yoktur.
