# FHB

- boundary_first / least_privilege / explicit_state は常にtrue（1つでもfalseはBLOCK）
- data_classification は PUBLIC/PROTECTED/SECRET のみ
- pii_handling は NONE/ANON/CONSENTED_SHORT_TERM のみ
- CONSENTED_SHORT_TERM は requires_human_approval=true が必須（違反はBLOCK）
- attack_surface_change=MAJOR はWARN（人間レビュー強推奨）

