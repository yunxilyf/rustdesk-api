/* 控制台端到端冒烟（Playwright）：初始化/登录 → 八个菜单 → 退出登录。
 *
 * 用法（先启动 runserver）：
 *   set SMOKE_BASE=http://127.0.0.1:21114
 *   node e2e/console_e2e.js
 *
 * 依赖 playwright-core 与本机 Chrome/Chromium：
 *   npm i playwright-core
 *   CHROME_PATH 可覆盖浏览器路径。
 */
const path = require('path')
const { chromium } = require('playwright-core')

const BASE = (process.env.SMOKE_BASE || 'http://127.0.0.1:21114').replace(/\/$/, '')
const USER = process.env.E2E_USER || 'admin'
const PWD = process.env.E2E_PWD || 'Admin@2026'
const CHROME =
  process.env.CHROME_PATH ||
  path.join(process.env.LOCALAPPDATA || '', 'ms-playwright', 'chromium-1248', 'chrome-win64', 'chrome.exe')

const MENUS = [
  ['概览', '/dashboard'],
  ['设备', '/devices'],
  ['地址簿', '/addressbooks'],
  ['设备分组', '/groups'],
  ['用户', '/users'],
  ['连接日志', '/conn-logs'],
  ['文件日志', '/file-logs'],
  ['个人设置', '/settings'],
]

const results = []
function check(name, ok, detail = '') {
  results.push({ name, ok })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${ok || !detail ? '' : ' | ' + detail}`)
}

async function main() {
  const browser = await chromium.launch({ executablePath: CHROME, headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const pageErrors = []
  const consoleErrors = []
  page.on('pageerror', (e) => pageErrors.push(String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text())
  })

  await page.goto(`${BASE}/console/`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(800)

  const boxUser = await page.locator('.login-card .t-input').first().boundingBox().catch(() => null)
  const boxBtn = await page.locator('.login-card .t-button').first().boundingBox().catch(() => null)
  check('登录输入框与按钮对齐', !!boxUser && !!boxBtn && Math.abs(boxUser.width - boxBtn.width) < 2,
    `${boxUser && boxUser.width} vs ${boxBtn && boxBtn.width}`)

  const title = await page.locator('h1.login-title').innerText().catch(() => '')
  if (title.includes('初始化')) {
    await page.getByPlaceholder('用户名').fill(USER)
    await page.getByPlaceholder('密码', { exact: true }).fill(PWD)
    await page.getByPlaceholder('确认密码').fill(PWD)
    await page.getByRole('button', { name: '创建管理员' }).click()
    check('首次初始化管理员', true)
  } else {
    await page.getByPlaceholder('用户名').fill(USER)
    await page.getByPlaceholder('密码', { exact: true }).fill(PWD)
    await page.getByRole('button', { name: '登 录' }).click()
    check('管理员登录', true)
  }

  await page.waitForURL(/#\/(dashboard|setup)/, { timeout: 15000 }).catch(() => {})
  const hash = await page.evaluate(() => location.hash)
  const hashPath = hash.split('?')[0]
  check('登录后进入概览', hashPath === '#/dashboard' || hashPath === '#/setup', hash)

  await page.waitForSelector('.app-menu .t-menu__item', { timeout: 15000 }).catch(() => {})
  const menuCount = await page.locator('.app-menu .t-menu__item').count()
  check('菜单项数量为 8', menuCount === 8, `count=${menuCount}`)

  for (const [label, expected] of MENUS) {
    const item = page.locator('.app-menu').getByText(label, { exact: true })
    if ((await item.count()) === 0) {
      check(`菜单「${label}」存在`, false, 'not found')
      continue
    }
    await item.first().click()
    await page.waitForTimeout(600)
    const current = await page.evaluate(() => location.hash)
    check(`菜单「${label}」跳转 ${expected}`, current.includes(expected), current)
    const bodyText = await page.locator('.app-content').innerText().catch(() => '')
    check(`页面「${label}」渲染`, bodyText.trim().length > 0, 'empty content')
  }

  const crumb = await page.locator('.crumb').innerText().catch(() => '')
  check('面包屑显示当前页面', crumb.trim().length > 0, crumb)

  // 退出登录
  await page.locator('.user-chip').click()
  await page.waitForTimeout(300)
  const logout = page.getByText('退出登录', { exact: true })
  if ((await logout.count()) > 0) {
    await logout.first().click()
    await page.waitForTimeout(800)
    const after = await page.evaluate(() => location.hash)
    check('退出登录回到登录页', after.includes('login'), after)
  } else {
    check('退出登录菜单可用', false, 'dropdown item missing')
  }

  check('无 JS 运行时错误', pageErrors.length === 0, pageErrors[0] || '')
  // 登录页会主动探测 /api/console/me，匿名时 401 属预期，仅过滤这一条资源错误
  const realConsoleErrors = consoleErrors.filter((t) => !/401 \(Unauthorized\)/.test(t))
  check('无控制台错误', realConsoleErrors.length === 0, realConsoleErrors[0] || '')

  await browser.close()
  const failed = results.filter((r) => !r.ok)
  console.log(`\n==== E2E ${results.length - failed.length}/${results.length} passed, ${failed.length} failed ====`)
  process.exit(failed.length === 0 ? 0 : 1)
}

main().catch((e) => {
  console.error('FATAL', e)
  process.exit(2)
})
