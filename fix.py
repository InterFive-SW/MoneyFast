import sys

with open('frontend/src/pages/Home.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if 'Toplam' in line and 'Varl' in line:
        start_idx = i - 1
        break

if start_idx != -1:
    end_idx = start_idx
    while end_idx < len(lines):
        if '</section>' in lines[end_idx]:
            break
        end_idx += 1

    print(f'Replacing from {start_idx} to {end_idx}')

    new_content = '''        <section className="rounded-2xl border border-slate-800 bg-black/40 backdrop-blur-md p-5">
          <h2 className="text-sm font-semibold text-white">Toplam Varlık</h2>
          {slices.length === 0 ? (
            <p className="mt-6 text-sm text-slate-400">Gösterilecek bakiye yok.</p>
          ) : (
            <div className="mt-4">
              <RingChart
                data={slices}
                totalValue={formatMoney(total)}
                totalLabel="Toplam Varlık"
                size={220}
              />
            </div>
          )}
          {unconvertible.length > 0 && (
            <p className="mt-3 text-xs text-amber-400">
              {[...new Set(unconvertible)].join(', ')} kuru bilinmediği için toplama dahil
              edilmedi.
            </p>
          )}
        </section>\n'''

    lines[start_idx:end_idx+1] = [new_content]

    with open('frontend/src/pages/Home.tsx', 'w', encoding='utf-8') as f:
        f.writelines(lines)
