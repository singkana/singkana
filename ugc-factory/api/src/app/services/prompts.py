SCRIPT_SCHEMA_HINT = """
出力は必ずJSON。自由文禁止。
キー: variants(list)
variants[*]: variant_index(int), hook(str), body(str), cta(str), full_script(str),
captions(list[{t:number,text:string}]),
shot(object{scene,camera,tone,gesture:list[str]}),
compliance(object{no_medical_claim:boolean,no_before_after:boolean})
"""


def render_prompt(product_meta: dict, target_count: int) -> str:
    product_name = product_meta.get("product_name", "")
    usp = product_meta.get("usp", "")
    target = product_meta.get("target", "")
    tone = product_meta.get("tone", "casual")

    return f"""
あなたはTikTok/Reels向けUGC台本ライター。
{SCRIPT_SCHEMA_HINT}

制約:
- 冒頭3秒に体験フック
- 誇大表現禁止、医療/治療の断定禁止
- 「ビフォーアフター」断定は禁止（no_before_after=true）
- トーン: {tone}
- ターゲット: {target}
- 商品: {product_name}
- 訴求: {usp}

出力:
- variants を {target_count} 本生成
- captions は 15秒想定で3〜6行
- hook/body/ctaは短く強く
""".strip()

