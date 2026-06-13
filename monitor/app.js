// ===== CONSTANTS =====
const RESUME_FILES = [
  {name:'SIVA SHANKAR_3-2-2025.pdf',size:'318 KB',type:'pdf'},
  {name:'SIVASHANKAR-14-03-2026.docx',size:'13.3 KB',type:'docx'},
  {name:'SIVASHANKAR-14-03-2026.pdf',size:'577 KB',type:'pdf'},
  {name:'SIVASHANKAR_7-3-2026.docx',size:'14 KB',type:'docx'},
  {name:'Siva_Shankar_06092026.docx',size:'13.6 KB',type:'docx'},
  {name:'Siva_Shankar_25-04-2026.pdf',size:'108 KB',type:'pdf'},
  {name:'Siva_Shankar_30052026.docx',size:'14.6 KB',type:'docx'},
  {name:'Siva_Shankar_6-02-26.docx',size:'35.6 KB',type:'docx'},
  {name:'Siva_Shankar_9-5-2026_Resume.docx',size:'19.6 KB',type:'docx'},
  {name:'Siva_Shankar_CV.docx',size:'14.7 KB',type:'docx'},
  {name:'Siva_Shankar_ResuMe.docx',size:'15.8 KB',type:'docx'},
  {name:'Siva_Shankar_Resume_6062026.docx',size:'17.6 KB',type:'docx'},
];

const SITE_META = {
  linkedin: {name:'LinkedIn',     logo:'💼', cls:'li', url:'linkedin.com',    color:'#0a66c2'},
  naukri:   {name:'Naukri',       logo:'🔍', cls:'nk', url:'naukri.com',      color:'#3399ff'},
  indeed:   {name:'Indeed India', logo:'🌐', cls:'in', url:'in.indeed.com',   color:'#2557a7'},
  shine:    {name:'Shine',        logo:'✨', cls:'sh', url:'shine.com',       color:'#ff8c00'},
  monster:  {name:'Monster',      logo:'👾', cls:'mn', url:'monsterindia.com',color:'#6632e1'},
  company_careers: {name:'Company Careers', logo:'🏢', cls:'cc', url:'Various', color:'#10b981'},
  system:   {name:'System',       logo:'⚙️', cls:'sys',url:'',                color:'#6366f1'},
};

// ===== STATE =====
let state = {
  applications: [],
  logs: [],
  filteredApps: [],
  appsPage: 1,
  appsPerPage: 15,
  currentPage: 'dashboard',
  isDemo: true, // true when data/applications.json not available
};

// ===== DATA LOADING =====
async function loadData() {
  const btn = document.querySelector('.refresh-btn');
  if (btn) btn.classList.add('spinning');

  try {
    // data/ is served alongside index.html on GitHub Pages (see deploy.yml)
    const ts = Date.now();
    const [appsRes, logsRes] = await Promise.all([
      fetch('data/applications.json?t=' + ts).catch(() => null),
      fetch('data/logs.json?t=' + ts).catch(() => null),
    ]);

    if (appsRes && appsRes.ok) {
      const data = await appsRes.json();
      if (Array.isArray(data)) {
        state.applications = data;
        state.isDemo = false;
        const now = new Date().toLocaleTimeString('en-IN', {hour:'2-digit',minute:'2-digit',hour12:true});
        document.getElementById('dataSourceNote').innerHTML =
          '<span class="dot-live"></span> Live bot data — ' + state.applications.length + ' records · updated ' + now;
      } else {
        loadDemoData();
      }
    } else {
      loadDemoData();
    }

    if (logsRes && logsRes.ok) {
      const logData = await logsRes.json();
      if (Array.isArray(logData)) {
        state.logs = logData;
      } else if (state.isDemo) {
        loadDemoLogs();
      }
    } else if (state.isDemo) {
      loadDemoLogs();
    }

  } catch (e) {
    loadDemoData();
  }

  if (btn) btn.classList.remove('spinning');
  refreshCurrentPage();
  showToast('📊 Data refreshed', 'info');
}

// Auto-refresh every 5 minutes so the dashboard stays current
setInterval(loadData, 5 * 60 * 1000);

function loadDemoData() {
  state.isDemo = true;
  document.getElementById('dataSourceNote').innerHTML =
    '<span class="dot-live" style="background:var(--amber)"></span> Demo mode (bot not running yet)';
  // Generate realistic demo data
  const companies = ['Google','Microsoft','TCS','Infosys','Wipro','Accenture','Capgemini','HCL','IBM','Deloitte','Cognizant','Zoho','Freshworks','Razorpay','PhonePe','Flipkart','Amazon','Adobe','Oracle','SAP'];
  const roles = ['Software Engineer','Full Stack Developer','.NET Developer','Java Developer','Python Developer','React Developer','Node.js Developer','Senior Developer','Tech Lead'];
  const locs = ['Bangalore','Chennai','Hyderabad','Remote','UK','Australia','Singapore'];
  const sites = ['linkedin','naukri','indeed','shine','monster','company_careers'];
  const statuses = ['applied','applied','applied','viewed','shortlisted','rejected','callback'];

  state.applications = [];
  const now = new Date();
  for (let i = 0; i < 120; i++) {
    const d = new Date(now);
    if (i < 28) { d.setHours(Math.floor(Math.random()*23), Math.floor(Math.random()*60)); }
    else { d.setDate(d.getDate() - Math.floor(Math.random()*13 + 1)); d.setHours(Math.floor(Math.random()*23), Math.floor(Math.random()*60)); }
    state.applications.push({
      id: Math.random().toString(36).slice(2,10),
      site: sites[Math.floor(Math.random()*sites.length)],
      company: companies[Math.floor(Math.random()*companies.length)],
      role: roles[Math.floor(Math.random()*roles.length)],
      location: locs[Math.floor(Math.random()*locs.length)],
      job_url: '#',
      match_score: Math.floor(Math.random()*27)+72,
      resume_used: 'Siva_Shankar_Resume_6062026_tailored.docx',
      status: statuses[Math.floor(Math.random()*statuses.length)],
      applied_at: d.toISOString(),
    });
  }
  state.applications.sort((a,b) => new Date(b.applied_at) - new Date(a.applied_at));
}

function loadDemoLogs() {
  const now = Date.now();
  const msgs = [
    {level:'INFO',    msg:'Job Bot started — 12 AM to 11 PM window active',               site:'system'},
    {level:'SUCCESS', msg:'All 5 job sites initialized successfully',                      site:'system'},
    {level:'AI',      msg:'Claude Sonnet 4.6 engine ready — resume tailoring enabled',    site:'ai'},
    {level:'INFO',    msg:'LinkedIn: Scanning for Software Engineer jobs in Bangalore',   site:'linkedin'},
    {level:'AI',      msg:'Tailoring resume for TCS — Full Stack Developer (94% match)', site:'ai'},
    {level:'SUCCESS', msg:'✅ Applied: Full Stack Developer @ TCS | Bangalore | 94%',    site:'linkedin'},
    {level:'AI',      msg:'Tailoring resume for Google — Software Engineer (97% match)', site:'ai'},
    {level:'SUCCESS', msg:'✅ Applied: Software Engineer @ Google | Remote | 97%',       site:'linkedin'},
    {level:'INFO',    msg:'Naukri: Scanning .NET Developer jobs in Chennai',              site:'naukri'},
    {level:'SUCCESS', msg:'✅ Applied: .NET Developer @ Infosys | Chennai | 89%',        site:'naukri'},
    {level:'WARN',    msg:'Indeed: CAPTCHA detected — waiting 30s before retry',         site:'indeed'},
    {level:'SUCCESS', msg:'Indeed: Resumed after CAPTCHA — continuing applications',     site:'indeed'},
    {level:'AI',      msg:'Batch of 12 resumes tailored in 1m 48s',                     site:'ai'},
    {level:'INFO',    msg:'Shine: Scanning React Developer jobs — Remote',               site:'shine'},
    {level:'SUCCESS', msg:'✅ Applied: React Developer @ Zoho | Remote | 91%',           site:'shine'},
    {level:'SUCCESS', msg:'Monster: Applied to 8 jobs in this batch',                   site:'monster'},
    {level:'INFO',    msg:'Cycle complete — 28 applications submitted. Sleeping 90 min.',site:'system'},
  ];
  state.logs = msgs.map((m,i) => ({...m, ts: new Date(now - (msgs.length-i)*120000).toISOString()}));
}

// ===== REFRESH CURRENT PAGE =====
function refreshCurrentPage() {
  const p = state.currentPage;
  if (p === 'dashboard')    renderDashboard();
  if (p === 'applications') { state.filteredApps = state.applications; renderAppsTable(); }
  if (p === 'sites')        renderSitesPage();
  if (p === 'resumes')      renderResumePage();
  if (p === 'scheduler')    renderScheduler();
  if (p === 'analytics')    renderCharts();
  if (p === 'logs')         renderLogsPage();
}

// ===== NAVIGATION =====
function navigate(el, page) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const navEl = el?.closest ? el.closest('.nav-item') || el : el;
  if (navEl?.classList) navEl.classList.add('active');
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const pg = document.getElementById('page-' + page);
  if (pg) pg.classList.add('active');
  state.currentPage = page;
  const TITLES = {
    dashboard:    ['Dashboard',      'Real-time job application monitor'],
    applications: ['Applications',   'All applications across LinkedIn, Naukri, Indeed, Shine, Monster'],
    sites:        ['Job Sites',      '5 connected job portals status and metrics'],
    resumes:      ['Resume Vault',   'Base resumes from E:\\SivaShankar\\Resume + AI-tailored copies'],
    scheduler:    ['Scheduler',      'Windows Task Scheduler • 24/7 Continuous Mode'],
    analytics:    ['Analytics',      'Deep insights and application trends'],
    logs:         ['Live Logs',      'Real-time system logs from the automation bot'],
  };
  document.getElementById('pageTitle').textContent = TITLES[page][0];
  document.getElementById('pageSubtitle').textContent = TITLES[page][1];
  refreshCurrentPage();
}

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('collapsed');
  document.getElementById('mainContent').classList.toggle('full');
}

// ===== UTILS =====
function todayApps() {
  const today = new Date().toDateString();
  return state.applications.filter(a => new Date(a.applied_at).toDateString() === today);
}
function siteApps(site) { return state.applications.filter(a => a.site === site); }
function todaySiteApps(site) { return todayApps().filter(a => a.site === site); }
function fmt(d) { return new Date(d).toLocaleString('en-IN',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',hour12:true}); }
function fmtTime(d) { return new Date(d).toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',hour12:true}); }
function msAgo(ts) {
  const s = Math.floor((Date.now() - new Date(ts))/1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s/60)}m ago`;
  return `${Math.floor(s/3600)}h ago`;
}
function isBotActive() { return true; }

// ===== DASHBOARD =====
function renderDashboard() {
  const today = todayApps();
  const callbacks = state.applications.filter(a => a.status === 'callback');
  const rate = state.applications.length ? ((callbacks.length / state.applications.length)*100).toFixed(1) : 0;

  animCount('kpiToday',    today.length);
  animCount('kpiTotal',    state.applications.length);
  animCount('kpiResumes',  state.applications.length);
  animCount('kpiCallbacks',callbacks.length);

  document.getElementById('kpiTodayDate').textContent = new Date().toLocaleDateString('en-IN',{day:'2-digit',month:'short'});
  document.getElementById('kpiCallbackRate').textContent = `${rate}% response rate`;

  // Ring
  const rv = document.getElementById('ringValue');
  if (rv) rv.textContent = today.length;
  const ring = document.getElementById('ringFill');
  if (ring) {
    const circ = 2*Math.PI*75;
    const offset = circ - Math.min(today.length/60, 1)*circ;
    setTimeout(() => ring.setAttribute('stroke-dashoffset', offset), 300);
  }
  document.getElementById('statLinkedIn').textContent = todaySiteApps('linkedin').length;
  document.getElementById('statNaukri').textContent   = todaySiteApps('naukri').length;
  document.getElementById('statIndeed').textContent   = todaySiteApps('indeed').length;

  const badge = document.getElementById('progressBadge');
  if (badge) { badge.textContent = isBotActive() ? 'Active' : 'Standby'; badge.classList.toggle('paused', !isBotActive()); }

  renderActivityFeed();
  renderRecentTable();
  renderSiteHealth();
  updateTimeline();
}

function renderActivityFeed() {
  const feed = document.getElementById('activityFeed');
  if (!feed) return;
  const recent = state.applications.slice(0, 12);
  const logs_ai = state.logs.filter(l => l.level === 'AI').slice(-6);
  const items = [];
  recent.forEach(a => items.push({ type:'apply', title:`Applied to ${a.role} at ${a.company}`, sub:`${SITE_META[a.site]?.name||a.site} • ${a.location} • ${a.match_score}% match`, ts:a.applied_at }));
  logs_ai.forEach(l => items.push({ type:'ai', title:l.msg, sub:`Claude Sonnet 4.6`, ts:l.ts }));
  items.sort((a,b) => new Date(b.ts) - new Date(a.ts));

  feed.innerHTML = items.slice(0,12).map(item => `
    <div class="activity-item">
      <div class="act-icon ${item.type==='ai'?'act-ai':'act-apply'}">${item.type==='ai'?'🤖':'✅'}</div>
      <div class="act-body">
        <div class="act-title">${item.title}</div>
        <div class="act-sub">${item.sub}</div>
      </div>
      <div class="act-time">${msAgo(item.ts)}</div>
    </div>
  `).join('');
}

function renderRecentTable() {
  const tbody = document.getElementById('recentTableBody');
  if (!tbody) return;
  tbody.innerHTML = state.applications.slice(0,8).map(a => `
    <tr>
      <td><strong>${a.company}</strong></td>
      <td>${a.role}</td>
      <td><span class="site-tag tag-${a.site}">${SITE_META[a.site]?.name||a.site}</span></td>
      <td>
        <div class="match-bar">
          <div class="match-track"><div class="match-fill" style="width:${a.match_score}%"></div></div>
          <span class="match-pct">${a.match_score}%</span>
        </div>
      </td>
      <td><span class="status-chip chip-${a.status}">${a.status.charAt(0).toUpperCase()+a.status.slice(1)}</span></td>
      <td style="color:var(--text-muted);font-family:var(--mono);font-size:0.75rem">${fmtTime(a.applied_at)}</td>
    </tr>
  `).join('');
}

function renderSiteHealth() {
  const c = document.getElementById('siteHealthItems');
  if (!c) return;
  const sites = ['linkedin','naukri','indeed','shine','monster','company_careers'];
  c.innerHTML = sites.map(s => {
    const m = SITE_META[s];
    const count = siteApps(s).length;
    const todayCount = todaySiteApps(s).length;
    return `
      <div class="health-item">
        <div class="health-icon h-icon-ok">${m.logo}</div>
        <div style="flex:1">
          <div class="health-label">${m.name}</div>
          <div class="health-value health-ok">${todayCount} today · ${count} total</div>
        </div>
        <span class="site-pill ${m.cls}" style="padding:3px 10px;font-size:0.68rem">Active</span>
      </div>
    `;
  }).join('');
}

function updateTimeline() {
  const h = new Date().getHours(), m = new Date().getMinutes();
  const mins = h*60+m, total = 24*60;
  const ta = document.getElementById('timelineActive');
  const tc = document.getElementById('timelineCursor');
  if (ta) ta.style.width = '100%';
  if (tc) tc.style.left  = (mins/total*100)   + '%';
  const nrt = document.getElementById('nextRunTime');
  if (nrt) {
    nrt.textContent = '⚡ Running 24/7 continuously';
    nrt.style.color = 'var(--green)';
  }
}

// ===== ALL APPS =====
function filterApps() {
  const site   = document.getElementById('siteFlt')?.value   || 'all';
  const status = document.getElementById('statusFlt')?.value || 'all';
  const search = (document.getElementById('searchFlt')?.value || '').toLowerCase();
  state.filteredApps = state.applications.filter(a => {
    if (site   !== 'all' && a.site   !== site)   return false;
    if (status !== 'all' && a.status !== status) return false;
    if (search && !a.company.toLowerCase().includes(search) && !a.role.toLowerCase().includes(search)) return false;
    return true;
  });
  state.appsPage = 1;
  renderAppsTable();
  document.getElementById('appCount').textContent = `${state.filteredApps.length} applications`;
}

function renderAppsTable() {
  filterApps();
  const tbody = document.getElementById('allAppsBody');
  if (!tbody) return;
  const start = (state.appsPage-1)*state.appsPerPage;
  const slice = state.filteredApps.slice(start, start+state.appsPerPage);
  tbody.innerHTML = slice.map((a,i) => `
    <tr>
      <td style="color:var(--text-dim)">${start+i+1}</td>
      <td><strong>${a.company}</strong></td>
      <td>${a.role}</td>
      <td style="color:var(--text-muted)">${a.location}</td>
      <td><span class="site-tag tag-${a.site}">${SITE_META[a.site]?.name||a.site}</span></td>
      <td>
        <div class="match-bar">
          <div class="match-track" style="width:60px"><div class="match-fill" style="width:${a.match_score}%"></div></div>
          <span class="match-pct">${a.match_score}%</span>
        </div>
      </td>
      <td style="font-size:0.7rem;color:var(--text-muted);font-family:var(--mono)">${(a.resume_used||'').slice(0,24)}...</td>
      <td><span class="status-chip chip-${a.status}">${a.status.charAt(0).toUpperCase()+a.status.slice(1)}</span></td>
      <td style="color:var(--text-muted);font-family:var(--mono);font-size:0.75rem">${fmt(a.applied_at)}</td>
    </tr>
  `).join('');
  renderPagination();
}

function renderPagination() {
  const pg = document.getElementById('pagination');
  if (!pg) return;
  const total = Math.ceil(state.filteredApps.length / state.appsPerPage);
  pg.innerHTML = Array.from({length:Math.min(total,8)},(_,i) => `
    <button class="page-btn ${i+1===state.appsPage?'active':''}" onclick="state.appsPage=${i+1};renderAppsTable()">${i+1}</button>
  `).join('');
}

// ===== SITES PAGE =====
function renderSitesPage() {
  const g = document.getElementById('sitesGrid');
  if (!g) return;
  g.innerHTML = Object.entries(SITE_META).filter(([k]) => k!=='system').map(([key, m]) => {
    const total = siteApps(key).length;
    const todays = todaySiteApps(key).length;
    const callbacks = state.applications.filter(a => a.site===key && a.status==='callback').length;
    return `
      <div class="site-card">
        <div class="site-card-header">
          <div class="site-logo site-${key.slice(0,2)}">${m.logo}</div>
          <div>
            <div class="site-name">${m.name}</div>
            <div class="site-url">${m.url}</div>
          </div>
          <span class="site-status-chip chip-active" style="margin-left:auto">Active</span>
        </div>
        <div class="site-stats">
          <div class="site-stat">
            <div class="site-stat-v" style="color:${m.color}">${todays}</div>
            <div class="site-stat-l">Today</div>
          </div>
          <div class="site-stat">
            <div class="site-stat-v">${total}</div>
            <div class="site-stat-l">Total</div>
          </div>
          <div class="site-stat">
            <div class="site-stat-v" style="color:var(--green)">${callbacks}</div>
            <div class="site-stat-l">Callbacks</div>
          </div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">
          <span style="font-size:0.75rem;color:var(--text-muted)">Search: Software Engineer, Full Stack, .NET, Java, React</span>
        </div>
      </div>
    `;
  }).join('');
}

// ===== RESUME PAGE =====
function renderResumePage() {
  const today = new Date().toLocaleDateString('en-GB').replace(/\//g,'-');
  const el = document.getElementById('todayFolderName');
  if (el) el.textContent = today;
  document.getElementById('tailoredCountBig').textContent = todayApps().length;

  const grid = document.getElementById('resumeGrid');
  if (grid) {
    grid.innerHTML = RESUME_FILES.map((f,i) => `
      <div class="resume-file-card ${i===RESUME_FILES.length-1?'resume-active':''}">
        <div class="resume-icon">${f.type==='pdf'?'📄':'📝'}</div>
        <div>
          <div class="resume-name">${f.name}</div>
          <div class="resume-size">${f.size} · ${f.type.toUpperCase()} ${i===RESUME_FILES.length-1?'· <span style="color:var(--green)">Base File ✓</span>':''}</div>
        </div>
      </div>
    `).join('');
  }

  const tl = document.getElementById('tailoredList');
  if (tl) {
    const apps = todayApps().slice(0, 20);
    tl.innerHTML = apps.length === 0
      ? '<div style="color:var(--text-muted);padding:20px">No tailored resumes yet today — bot will generate them as it applies.</div>'
      : apps.map(a => `
        <div class="tailored-item">
          <div class="tailored-left">
            <div style="font-size:22px">🤖</div>
            <div>
              <div class="tailored-company">${a.company} — ${a.role}</div>
              <div class="tailored-meta">${fmtTime(a.applied_at)} · ${a.match_score}% match · ${SITE_META[a.site]?.name||a.site}</div>
            </div>
          </div>
          <span class="ai-tag">AI TAILORED</span>
        </div>
      `).join('');
  }
}

// ===== SCHEDULER =====
function renderScheduler() {
  updateTimeline();
  renderHeatmap();
}

function renderHeatmap() {
  const hmap = document.getElementById('heatmap');
  if (!hmap) return;
  const today = todayApps();
  // Count per hour
  const counts = Array(24).fill(0);
  today.forEach(a => { const h = new Date(a.applied_at).getHours(); counts[h]++; });
  const maxV = Math.max(...counts, 1);
  document.getElementById('heatmapMax').textContent = maxV + '+';

  hmap.innerHTML = counts.map((c,h) => {
    const intensity = c/maxV;
    const bg = c===0 ? 'var(--surface)' : `rgba(99,102,241,${0.15+intensity*0.75})`;
    return `<div class="hmap-cell" style="background:${bg}" title="${h}:00 — ${c} applications"></div>`;
  }).join('');

  // Hour labels
  const existing = hmap.parentElement.querySelector('.hmap-label-row');
  if (!existing) {
    const labels = document.createElement('div');
    labels.className = 'hmap-label-row';
    ['12a','3a','6a','9a','12p','3p','6p','9p','11p'].forEach(l => {
      const s = document.createElement('span'); s.textContent = l; labels.appendChild(s);
    });
    hmap.parentElement.insertBefore(labels, hmap.nextSibling);
  }
}

// ===== CHARTS =====
function renderCharts() {
  renderDailyChart();
  renderStatusChart();
  renderSiteChart();
  renderMatchChart();
}

function renderDailyChart() {
  const canvas = document.getElementById('dailyChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.parentElement.clientWidth - 48, H = 200;
  canvas.width = W; canvas.height = H;

  const days = 14;
  const labels = [], data = [];
  for (let i=0; i<days; i++) {
    const d = new Date(); d.setDate(d.getDate()-(days-1-i));
    const ds = d.toDateString();
    labels.push(d.toLocaleDateString('en-IN',{day:'2-digit',month:'short'}));
    data.push(state.applications.filter(a => new Date(a.applied_at).toDateString()===ds).length);
  }

  const pad={top:20,right:20,bottom:36,left:36};
  const gW=W-pad.left-pad.right, gH=H-pad.top-pad.bottom;
  const max=Math.max(...data)+3;
  const bW=(gW/days)-8;

  ctx.clearRect(0,0,W,H);
  for (let i=0;i<=4;i++) {
    const y=pad.top+gH-(i/4)*gH;
    ctx.beginPath(); ctx.strokeStyle='rgba(255,255,255,0.05)'; ctx.lineWidth=1;
    ctx.moveTo(pad.left,y); ctx.lineTo(pad.left+gW,y); ctx.stroke();
    ctx.fillStyle='rgba(148,163,184,0.5)'; ctx.font='10px Inter'; ctx.textAlign='right';
    ctx.fillText(Math.round(i/4*max), pad.left-4, y+4);
  }
  data.forEach((v,i) => {
    const x=pad.left+i*(gW/days)+(gW/days-bW)/2;
    const bH=Math.max((v/max)*gH,2), y=pad.top+gH-bH;
    const isToday=i===days-1;
    const grad=ctx.createLinearGradient(0,y,0,y+bH);
    grad.addColorStop(0, isToday?'#6366f1':'#3b82f6');
    grad.addColorStop(1, isToday?'rgba(99,102,241,0.3)':'rgba(59,130,246,0.2)');
    ctx.fillStyle=grad;
    ctx.beginPath(); ctx.roundRect(x,y,bW,bH,3); ctx.fill();
    if (v>0) { ctx.fillStyle='rgba(255,255,255,0.7)'; ctx.font='10px Inter'; ctx.textAlign='center'; ctx.fillText(v,x+bW/2,y-4); }
    if (i%2===0||isToday) { ctx.fillStyle='rgba(148,163,184,0.6)'; ctx.font='9px Inter'; ctx.textAlign='center'; ctx.fillText(labels[i],x+bW/2,H-6); }
  });
}

function renderStatusChart() {
  const canvas = document.getElementById('statusChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.parentElement.clientWidth - 48;
  canvas.height = 220;
  const W=canvas.width, H=canvas.height;
  const counts = {};
  ['applied','viewed','shortlisted','rejected','callback'].forEach(s => counts[s]=state.applications.filter(a=>a.status===s).length);
  const colors={applied:'#3b82f6',viewed:'#8b5cf6',shortlisted:'#f59e0b',rejected:'#ef4444',callback:'#10b981'};
  const total=Object.values(counts).reduce((a,b)=>a+b,0);
  const cx=W/2, cy=H/2-20, r=70;
  let angle=-Math.PI/2;
  Object.entries(counts).forEach(([k,v]) => {
    if (!v) return;
    const sweep=(v/total)*2*Math.PI;
    ctx.beginPath(); ctx.moveTo(cx,cy); ctx.arc(cx,cy,r,angle,angle+sweep);
    ctx.fillStyle=colors[k]; ctx.fill(); angle+=sweep;
  });
  ctx.beginPath(); ctx.arc(cx,cy,38,0,2*Math.PI); ctx.fillStyle='#0d1421'; ctx.fill();
  ctx.fillStyle='white'; ctx.font='bold 16px Inter'; ctx.textAlign='center'; ctx.fillText(total,cx,cy+5);
  ctx.fillStyle='rgba(148,163,184,0.7)'; ctx.font='10px Inter'; ctx.fillText('Total',cx,cy+18);
  // legend
  let lx=8, ly=H-28;
  Object.entries(counts).forEach(([k,v]) => {
    ctx.fillStyle=colors[k]; ctx.beginPath(); ctx.arc(lx+5,ly,5,0,2*Math.PI); ctx.fill();
    ctx.fillStyle='rgba(148,163,184,0.8)'; ctx.font='10px Inter'; ctx.textAlign='left';
    ctx.fillText(`${k} ${v}`, lx+14, ly+4);
    lx += 90; if (lx > W-80) { lx=8; ly+=16; }
  });
}

function renderSiteChart() {
  const canvas = document.getElementById('siteChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.parentElement.clientWidth - 48;
  canvas.height = 220;
  const W=canvas.width, H=canvas.height;
  const sites=['linkedin','naukri','indeed','shine','monster','company_careers'];
  const colors=['#0a66c2','#3399ff','#2557a7','#ff8c00','#6632e1','#10b981'];
  const counts=sites.map(s=>siteApps(s).length);
  const max=Math.max(...counts)+2;
  const pad={top:20,right:20,bottom:40,left:40};
  const gW=W-pad.left-pad.right, gH=H-pad.top-pad.bottom;
  const bW=gW/sites.length-12;

  ctx.clearRect(0,0,W,H);
  counts.forEach((v,i) => {
    const x=pad.left+i*(gW/sites.length)+6;
    const bH=Math.max((v/max)*gH,2), y=pad.top+gH-bH;
    const grad=ctx.createLinearGradient(0,y,0,y+bH);
    grad.addColorStop(0,colors[i]); grad.addColorStop(1,colors[i]+'44');
    ctx.fillStyle=grad;
    ctx.beginPath(); ctx.roundRect(x,y,bW,bH,4); ctx.fill();
    ctx.fillStyle='rgba(255,255,255,0.8)'; ctx.font='11px Inter'; ctx.textAlign='center';
    if (v>0) ctx.fillText(v,x+bW/2,y-5);
    ctx.fillStyle='rgba(148,163,184,0.7)'; ctx.font='10px Inter';
    ctx.fillText(SITE_META[sites[i]].name.split(' ')[0],x+bW/2,H-8);
  });
}

function renderMatchChart() {
  const canvas = document.getElementById('matchChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W=canvas.parentElement.clientWidth-48, H=160;
  canvas.width=W; canvas.height=H;
  const buckets=[{l:'70-75%',r:[70,76]},{l:'76-80%',r:[76,81]},{l:'81-85%',r:[81,86]},{l:'86-90%',r:[86,91]},{l:'91-95%',r:[91,96]},{l:'96-99%',r:[96,100]}];
  const counts=buckets.map(b=>state.applications.filter(a=>a.match_score>=b.r[0]&&a.match_score<b.r[1]).length);
  const max=Math.max(...counts)+1;
  const pad={top:20,right:20,bottom:36,left:36};
  const gW=W-pad.left-pad.right, gH=H-pad.top-pad.bottom;
  const bW=gW/buckets.length-10;
  ctx.clearRect(0,0,W,H);
  counts.forEach((v,i)=>{
    const x=pad.left+i*(gW/buckets.length)+5;
    const bH=Math.max((v/max)*gH,2), y=pad.top+gH-bH;
    const grad=ctx.createLinearGradient(0,y,0,y+bH);
    grad.addColorStop(0,'#10b981'); grad.addColorStop(1,'rgba(16,185,129,0.2)');
    ctx.fillStyle=grad; ctx.beginPath(); ctx.roundRect(x,y,bW,bH,4); ctx.fill();
    if (v>0){ctx.fillStyle='rgba(255,255,255,0.8)';ctx.font='10px Inter';ctx.textAlign='center';ctx.fillText(v,x+bW/2,y-4);}
    ctx.fillStyle='rgba(148,163,184,0.6)';ctx.font='9px Inter';ctx.textAlign='center';ctx.fillText(buckets[i].l,x+bW/2,H-6);
  });
}

// ===== LOGS =====
function renderLogsPage() {
  const term = document.getElementById('logTerminal');
  if (!term) return;
  const level = document.getElementById('logLevel')?.value || 'all';
  const logs = level==='all' ? state.logs : state.logs.filter(l=>l.level===level);
  term.innerHTML = logs.slice(-200).map(l => `
    <div class="log-line">
      <span class="log-ts">${new Date(l.ts).toLocaleTimeString('en-IN',{hour12:false})}</span>
      <span class="log-level level-${(l.level||'info').toLowerCase()}">${l.level}</span>
      <span class="log-ts" style="min-width:70px;color:var(--text-dim)">[${l.site||'system'}]</span>
      <span class="log-msg">${l.msg}</span>
    </div>
  `).join('');
  term.scrollTop = term.scrollHeight;
}

function clearLogs() { state.logs=[]; renderLogsPage(); }

// ===== CLOCK =====
function updateClock() {
  const el = document.getElementById('liveClock');
  if (el) el.textContent = new Date().toLocaleString('en-IN',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
}

// ===== TOAST =====
function showToast(msg, type='info') {
  const c=document.getElementById('toastContainer');
  const icons={info:'ℹ️',success:'✅',warn:'⚠️'};
  const t=document.createElement('div');
  t.className=`toast toast-${type}`;
  t.innerHTML=`<span class="toast-icon">${icons[type]||'ℹ️'}</span><span>${msg}</span>`;
  c.appendChild(t);
  setTimeout(()=>t.remove(),3200);
}

function animCount(id, target) {
  const el=document.getElementById(id); if (!el) return;
  let cur=0, step=Math.ceil(target/40);
  const t=setInterval(()=>{ cur=Math.min(cur+step,target); el.textContent=cur.toLocaleString(); if(cur>=target) clearInterval(t); },30);
}

// ===== INIT =====
window.addEventListener('DOMContentLoaded', () => {
  loadData();
  setInterval(updateClock, 1000);
  updateClock();
  // Auto-refresh every 60 seconds
  setInterval(() => {
    loadData().then(() => {
      if (state.currentPage === 'dashboard') renderDashboard();
    });
  }, 60000);
  // Live simulate additions every 30s (only in demo mode)
  setInterval(() => {
    if (state.isDemo && isBotActive()) {
      const s = ['linkedin','naukri','indeed','shine','monster'];
      const c = ['Google','Microsoft','TCS','Wipro','Infosys','Amazon','Adobe'];
      const r = ['Software Engineer','Full Stack Developer','.NET Developer','Java Developer'];
      const l = ['Bangalore','Remote','Chennai','UK','Australia'];
      const app = {
        id: Math.random().toString(36).slice(2,10),
        site: s[Math.floor(Math.random()*s.length)],
        company: c[Math.floor(Math.random()*c.length)],
        role: r[Math.floor(Math.random()*r.length)],
        location: l[Math.floor(Math.random()*l.length)],
        job_url: '#', match_score: Math.floor(Math.random()*27)+72,
        resume_used: 'Siva_Shankar_Resume_6062026_tailored.docx',
        status: 'applied',
        applied_at: new Date().toISOString(),
      };
      state.applications.unshift(app);
      if (state.currentPage === 'dashboard') renderDashboard();
    }
  }, 30000);
});
