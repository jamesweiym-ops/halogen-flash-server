import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "/app/.next/server/chunks/8499.js")
text = path.read_text()
old = (
    'if("response.reasoning_summary_text.delta"===c){let a=d.delta||"";'
    'return a?(0,f.k)({id:b.chatId,created:b.created,model:b.model||j.rP},'
    '(0,i.B)(a)):null}'
)
new = (
    'if("response.reasoning_summary_part.added"===c)return b.reasoningSummaryPartSeen=!0,null;'
    'if("response.reasoning_text.delta"===c){let a=d.delta||"";'
    'return a&&!b.reasoningSummaryPartSeen?'
    '(b.reasoningRawTextSeen=!0,(0,f.k)({id:b.chatId,created:b.created,model:b.model||j.rP},(0,i.B)(a))):null}'
    'if("response.reasoning_summary_text.delta"===c){let a=d.delta||"";'
    'return a&&!b.reasoningRawTextSeen?(0,f.k)({id:b.chatId,created:b.created,model:b.model||j.rP},(0,i.B)(a)):null}'
)
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected one old translator branch, found {count}")
path.write_text(text.replace(old, new))
print("patched", path)
