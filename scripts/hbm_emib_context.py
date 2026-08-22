from __future__ import annotations

import pathlib

ALERT = pathlib.Path("out/hbm_monthly_alert.md")
MARKER = "9) 말레이시아·Intel EMIB 관계"

BLOCK = """

9) 말레이시아·Intel EMIB 관계
• Intel EMIB(Embedded Multi-die Interconnect Bridge·기판 안의 작은 실리콘 브리지로 여러 칩을 고속 연결하는 2.5D 첨단 패키징)는 공식적으로 logic↔logic뿐 아니라 logic↔HBM 연결에 쓰입니다.
• Intel은 말레이시아 Penang에 대규모 첨단 패키징 시설을 구축해 왔고, Kulim에도 조립·테스트 생산거점을 운영·확장해 왔습니다.
• 따라서 한국→말레이시아 HSK 8542323000 수출 증가는 HBM이 첨단 패키징·조립 공정으로 이동하는 흐름을 볼 때 의미 있는 보조 신호가 될 수 있습니다.
• 다만 말레이시아향 수출 = 전부 HBM, 또는 전부 Intel/EMIB용이라는 뜻은 아닙니다. HSK 8542323000에는 HBM 외 복합 메모리도 포함될 수 있으므로 반드시 보조 대용지표로만 해석합니다.
• 해석 경로: 한국 HBM 생산 → 말레이시아 첨단 패키징·조립 거점 → EMIB 등으로 로직 칩과 HBM 결합 가능 → AI/HPC용 패키지 완성.
• Intel 공식 EMIB: https://www.intel.com/content/www/us/en/foundry/packaging.html
• Intel Malaysia 첨단 패키징 투자: https://newsroom.intel.com/intel-foundry/updates-intel-10-largest-construction-projects
""".rstrip()


def main() -> None:
    if not ALERT.exists():
        return
    text = ALERT.read_text(encoding="utf-8")
    if MARKER in text:
        return
    ALERT.write_text(text.rstrip() + BLOCK + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
