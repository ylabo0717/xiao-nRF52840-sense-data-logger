---
applyTo: "**/*.{cpp,cxx,cc,h,hpp}"
---

# C++ / Header Coding Rules

- コードは Google Style に従って整形する  
- 名前空間は `project::module` 形式で統一  
- ヘッダファイルにはインクルードガード、または `#pragma once` を必ず使用する  
- コメントは Doxygen スタイルを推奨する (`///` や `/** */`)  
- モダンC++を優先的に使用する（例：`std::span`, `concepts`, `constexpr`）  
- クラス名・構造体名は PascalCase、変数名は snake_case を徹底する  
- ポインタよりもスマートポインタを推奨 (`std::unique_ptr`, `std::shared_ptr`)  
