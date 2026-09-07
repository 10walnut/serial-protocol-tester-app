const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');
const root = __dirname;
const guide = JSON.parse(fs.readFileSync(path.join(root, 'guide.json'), 'utf8'));
const esc = text => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');

function image(name, cls = '') {
  return `<img class="shot ${cls}" src="assets/${name}" alt="软件操作截图">`;
}

function graphic(p) {
  if (p.visual === 'downloads') return `<div class="download-row"><b>中文版</b><span>默认中文界面 + 中文示例</span><code>SerialProtocolAssistant-ZH-CN.exe</code></div><div class="download-row english"><b>English</b><span>English UI + English sample</span><code>SerialProtocolAssistant-EN.exe</code></div><p class="graphic-note">两个版本功能相同，均支持软件内切换语言。</p>`;
  if (p.visual === 'installer') return `<div class="process-label">安装向导流程示意</div><div class="flow"><b>下载 signed 压缩包</b><span>↓</span><b>完整解压 → 运行安装程序</b><span>↓</span><b>完成向导 → 按提示重启</b><span>↓</span><b>检查 setupc.exe → 创建 COM 对</b></div>`;
  if (p.visual === 'verify') return `<div class="process-label">验收标准示意 · 不是当前机器设备列表</div><div class="tree"><strong>设备管理器</strong><p>└ 端口（COM 和 LPT）</p><p class="indent">├ … (COM10)</p><p class="indent">└ … (COM11)</p></div><div class="pair"><b>程序 A<br>COM10</b><span>↔</span><b>程序 B<br>COM11</b></div>`;
  if (p.visual === 'port-form') return `<div class="port-crop">${image(p.image)}</div><div class="flow port-flow"><b>检查路径</b><span>↓</span><b>两个不同、空闲的 COM 号</b><span>↓</span><b>创建端口对 → 刷新状态</b></div>`;
  let content = p.image ? image(p.image) : '';
  if (p.second_image) content += image(p.second_image, 'secondary');
  if (p.visual === 'host' || p.visual === 'device') content += `<div class="pair"><b>${p.visual === 'host' ? '本软件<br>上位机' : '本软件<br>下位机 / COM10'}</b><span>↔</span><b>${p.visual === 'host' ? '真实设备<br>实际串口号' : '外部上位机<br>COM11'}</b></div>`;
  return content;
}

const styles = `
*{box-sizing:border-box}body{margin:0;background:#dbe0e3;color:#17212a;font-family:"Microsoft YaHei",sans-serif;letter-spacing:0}header{max-width:1600px;margin:auto;padding:40px;background:#fff}header h1{font-size:34px}header a{color:#11685f;display:inline-block;margin:5px 18px 5px 0}section{position:relative;width:1600px;height:1200px;margin:32px auto;background:#f7f9fa;padding:54px 66px 90px;overflow:hidden}.eyebrow{display:flex;justify-content:space-between;color:#526470;font-size:22px;border-bottom:2px solid #17212a;padding-bottom:16px}.eyebrow b{color:#08796e}h2{font-size:48px;line-height:1.3;margin:28px 0 12px;font-weight:800}.subtitle{font-size:26px;line-height:1.5;color:#526470;margin:0 0 30px}.columns{display:grid;grid-template-columns:660px 750px;gap:58px}.instructions{counter-reset:step}.step{display:grid;grid-template-columns:46px 1fr;gap:16px;border-top:1px solid #cdd7dd;padding:23px 0;font-size:27px;line-height:1.65}.step:before{counter-increment:step;content:counter(step,decimal-leading-zero);font-size:28px;font-weight:800;color:#08796e}.shot{display:block;max-width:100%;max-height:570px;width:auto;height:auto;object-fit:contain;margin:0 auto 24px;border:1px solid #415059;border-radius:4px}.shot.secondary{max-height:335px}.visual{padding-top:9px}pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:22px 0 0;background:#e6efee;border-left:5px solid #08796e;padding:22px;font:24px/1.6 Consolas,"Microsoft YaHei",monospace}.result{font-size:25px;line-height:1.65;background:#17212a;color:white;padding:20px 24px;margin-top:22px}.note{font-size:22px;line-height:1.6;color:#596774;margin-top:18px}.footer{position:absolute;bottom:28px;left:66px;right:66px;border-top:1px solid #cdd7dd;padding-top:15px;display:flex;justify-content:space-between;font-size:19px;color:#596774}.links a{display:inline-block;color:#08796e;font-size:22px;margin:16px 22px 0 0}.download-row{padding:30px;border-top:5px solid #08796e;background:#e6efee;margin-bottom:30px}.download-row b{font-size:40px;display:block}.download-row span{font-size:25px;display:block;margin:14px 0}.download-row code{font-size:24px;font-weight:700}.download-row.english{border-top-color:#a25028;background:#f0e9e5}.graphic-note{font-size:26px;line-height:1.6}.process-label{font-size:21px;color:#687781;margin-bottom:22px}.flow{display:flex;flex-direction:column;align-items:stretch;text-align:center;gap:14px;font-size:28px}.flow b{padding:19px;background:#e6efee;border-left:5px solid #08796e}.flow span{color:#08796e}.pair{display:flex;gap:25px;align-items:center;justify-content:center;font-size:28px;margin:40px 0;line-height:1.7}.pair b{flex:1;text-align:center;background:#e6efee;border-top:5px solid #08796e;padding:26px 12px}.pair span{font-size:42px;color:#08796e}.tree{font-size:31px;line-height:1.4;padding:32px;background:#fff;border:1px solid #ccd5dc}.tree p{margin:18px 0}.tree .indent{padding-left:40px}.port-crop{height:166px;overflow:hidden;border:1px solid #415059;border-radius:4px;background:#202428}.port-crop .shot{width:100%;max-height:none;margin:0;border:0}.port-flow{margin-top:34px}.overview .columns{display:block}.overview .visual{display:none}.overview-shot{width:1100px;display:block;margin:20px auto 0;border:1px solid #415059}.overview .instructions{display:grid;grid-template-columns:1fr 1fr;gap:0 35px}.overview .step{font-size:22px;padding:12px 0;line-height:1.45}.overview .result{font-size:21px;padding:12px 18px;margin-top:14px}.overview .note{display:none}.overview h2{margin-top:22px}.overview .subtitle{margin-bottom:5px}.overview-markers{position:relative}.badge{position:absolute;background:#b34832;color:#fff;width:34px;height:34px;display:grid;place-items:center;border:2px solid #fff;border-radius:50%;font-size:21px;font-weight:800}.sources{max-width:1600px;margin:30px auto;padding:32px;background:#fff;font-size:20px}.sources a{color:#08796e}.sources p{line-height:1.8}@media print{body{background:white}header,.sources{display:none}section{margin:0;break-after:page}}`;

const overrides = `.overview-markers{width:1040px;margin:16px auto 0}.overview .overview-shot{width:1040px;max-height:none;margin:0}.overview .instructions{margin-top:16px}.overview .step{padding:10px 0}.overview .result{margin-top:8px}`;

function section(p, index) {
  const overview = p.visual === 'overview';
  const annotated = overview ? `<div class="overview-markers">${image(p.image, 'overview-shot')}<i class="badge" style="left:94%;top:1%">1</i><i class="badge" style="left:1%;top:12%">2</i><i class="badge" style="left:1%;top:30%">3</i><i class="badge" style="left:56%;top:67%">4</i></div>` : '';
  return `<section id="${p.id}" class="${overview ? 'overview' : ''}"><div class="eyebrow"><span>串口协议助手 / 图解使用说明</span><b>${String(index + 1).padStart(2, '0')} / ${guide.pages.length}</b></div><h2>${esc(p.title)}</h2><p class="subtitle">${esc(p.subtitle)}</p>${annotated}<div class="columns"><div><div class="instructions">${p.steps.map(s=>`<div class="step">${esc(s)}</div>`).join('')}</div><div class="result">${esc(p.result)}</div><p class="note">${esc(p.note || '')}</p><div class="links">${(p.links||[]).map(l=>`<a href="${esc(l.url)}">${esc(l.label)}</a>`).join('')}</div></div><div class="visual">${graphic(p)}${p.code?`<pre>${esc(p.code)}</pre>`:''}</div></div><div class="footer"><span>十个核桃 / 10walnut</span><span>软件 v${guide.version} · 先内部验证，再连接对端</span></div></section>`;
}

async function main() {
  const output = path.join(root, 'images');
  fs.mkdirSync(output,{recursive:true});
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=1600"><title>${guide.title}</title><style>${styles}</style></head><body><header><h1>${guide.title}</h1><p>13 步图解 · 下载、安装、协议导入、COM 配对与上下位机测试</p><nav>${guide.pages.map(p=>`<a href="#${p.id}">${esc(p.title.split('：')[0])}</a>`).join('')}</nav></header>${guide.pages.map(section).join('')}<div class="sources"><h3>资料与图示说明</h3><p>软件截图来自真实 Qt 控件，收发截图使用内置模拟。COM3、COM10、COM11 为配置示例。驱动安装流程与期望设备列表为明确标注的示意图，本次未安装驱动或创建端口。</p>${guide.sources.map(l=>`<p><a href="${l.url}">${l.label}</a></p>`).join('')}<p>com0com 由 Vyacheslav Frolov 及贡献者开发，按 GPL 分发。本指南引用官方入口，不重新分发驱动。</p></div></body></html>`;
  fs.writeFileSync(path.join(root,'index.html'),html.replace('</style>',`${overrides}</style>`),'utf8');
  const markdown = `# ${guide.title}\n\n适用软件 v${guide.version}。每张图可放大查看；[离线图解](index.html) 与本目录图片一起保存即可浏览。\n\n[中文版下载](https://github.com/10walnut/serial-protocol-tester-app/releases/latest/download/SerialProtocolAssistant-ZH-CN.exe) · [English download](https://github.com/10walnut/serial-protocol-tester-app/releases/latest/download/SerialProtocolAssistant-EN.exe) · [English guide](README.en.md)\n\n` + guide.pages.map(p=>`## ${p.title}\n\n${p.subtitle}\n\n![${p.title}](images/${p.id}.png)\n\n${p.steps.map((s,i)=>`${i+1}. ${s}`).join('\n')}\n\n${p.code?'```text\n'+p.code+'\n```\n\n':''}**预期结果：** ${p.result}\n\n${p.note}\n\n${(p.links||[]).map(l=>`[${l.label}](${l.url})`).join(' · ')}\n`).join('\n') + '\n## 来源与致谢\n\n' + guide.sources.map(l=>`- [${l.label}](${l.url})`).join('\n') + '\n\n软件截图为真实界面；报文截图使用内部模拟。安装流程和期望设备列表为示意，不代表本机已完成 com0com 创建与双向实测。感谢 Vyacheslav Frolov 及 com0com 贡献者。驱动遵循 GPL，本项目仅链接官方包。\n';
  fs.writeFileSync(path.join(root,'README.md'),markdown + '\n## 配套示例文件\n\n离线包内包含 [中文示例 JSON](examples/sample_protocol.zh.json) 和 [English sample JSON](examples/sample_protocol.en.json)。可通过“加载协议”重新载入对应示例。\n','utf8');
  const browser = await chromium.launch({headless:true,executablePath:process.env.BROWSER_EXE || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  try {
    const page = await browser.newPage({viewport:{width:1700,height:1300},deviceScaleFactor:1});
    await page.goto(pathToFileURL(path.join(root,'index.html')).href);
    await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode()));});
    const checks = await page.evaluate(()=>[...document.querySelectorAll('section')].map(el=>{
      const rect=el.getBoundingClientRect(), footer=el.querySelector('.footer').getBoundingClientRect(), errors=[];
      const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
      while(walker.nextNode()){
        const node=walker.currentNode;if(!node.textContent.trim()||node.parentElement.closest('.footer,.port-crop')||!node.parentElement.getClientRects().length)continue;
        const range=document.createRange();range.selectNodeContents(node);
        for(const box of range.getClientRects()) if(box.right>rect.right-10||box.left<rect.left||box.bottom>footer.top-8) errors.push(node.textContent.trim());
      }
      for(const img of el.querySelectorAll('.shot')) if(!img.closest('.port-crop,.overview-markers')&&img.getClientRects().length&&img.getBoundingClientRect().bottom>footer.top-8)errors.push('Image touches footer');
      return{id:el.id,width:rect.width,height:rect.height,errors};
    }));
    fs.writeFileSync(path.join(root,'layout-check.json'),JSON.stringify(checks,null,2));
    if(checks.some(c=>c.errors.length))throw new Error(JSON.stringify(checks.filter(c=>c.errors.length)));
    for(const p of guide.pages)await page.locator(`[id="${p.id}"]`).screenshot({path:path.join(output,`${p.id}.png`)});
    await page.setContent(`<html><style>body{margin:0;padding:20px;background:#dbe0e3}.grid{display:grid;grid-template-columns:repeat(4,400px);gap:16px}figure{margin:0}img{width:400px;height:300px}figcaption{font:16px sans-serif;padding:5px}</style><div class="grid">${guide.pages.map(p=>`<figure><img src="${pathToFileURL(path.join(output,p.id+'.png')).href}"><figcaption>${p.id}</figcaption></figure>`).join('')}</div></html>`);
    await page.evaluate(()=>Promise.all([...document.images].map(i=>i.decode())));
    await page.setViewportSize({width:1688,height:1420});
    await page.screenshot({path:path.join(root,'contact-sheet.png'),fullPage:true});
    console.log(JSON.stringify({pages:guide.pages.length,dimensions:'1600x1200',layoutErrors:0}));
  } finally {await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
