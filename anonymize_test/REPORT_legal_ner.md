# Юридическая модель распознавания сущностей как дополнение к обезличиванию

Писем: 80. После anonymizer.py осталось известных имён/фирм/мест: **7**; из них модель помечает: **6**.
Всего модель пометила в уже обезличенных текстах 95 сущностей, из них не относящихся к известным данным: **79** (1.0 на письмо) — это цена: лишние замены или работа проверяющему.

| Набор | Письмо | Вид | Осталось | Модель пометила |
|---|---|---|---|---|
| wild | wild_004 | Restaurantname#7 | Zur Eiche | да: Zur, Eiche |
| wild | wild_006 | Unternehmensname#8 | TechnoGmbH | да: Techn |
| wild | wild_007 | Unternehmensname#7 | Goldener Drache | да: Drache |
| wild | wild_023 | Firmenname#2 | Kanzlei Berg & Partner | да: Berg & Partner |
| wild | wild_033 | Name#1 | Stefanie Müller | да: Stefan |
| wild | wild_038 | Name#2 | hr. schuster | нет |
| wild2 | wild_040 | Firmenname#8 | Schreinerei Holz & mehr | да: Schr |