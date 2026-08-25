const $ = (selector) => document.querySelector(selector)
const $$ = (selector) => [...document.querySelectorAll(selector)]

const platformNames = { xiaohongshu: '小红书', douyin: '抖音', xianyu: '闲鱼' }
const state = { platform: 'xiaohongshu', kind: 'note', files: [], accounts: {}, pollTimer: null }

const form = $('#publishForm')
const account = $('#account')
const mediaInput = $('#media')
const dropzone = $('#dropzone')
const loginDialog = $('#loginDialog')
const progressDialog = $('#progressDialog')

function toast(message, error = false) {
  const node = $('#toast')
  node.textContent = message
  node.classList.toggle('error', error)
  node.classList.add('show')
  clearTimeout(node.timer)
  node.timer = setTimeout(() => node.classList.remove('show'), 3200)
}

async function api(path, options = {}) {
  const response = await fetch(path, options)
  let payload = {}
  try { payload = await response.json() } catch {}
  if (!response.ok) throw new Error(payload.detail || `请求失败 (${response.status})`)
  return payload
}

function platformReady() { return Boolean(state.accounts[state.platform]) }
function titleLimit() { return state.platform === 'douyin' ? 20 : 60 }

function updateAccountUI() {
  $$('.platform-stamp').forEach((button) => {
    const ready = Boolean(state.accounts[button.dataset.platform])
    const light = button.querySelector('.account-light')
    light.classList.toggle('ready', ready)
    light.setAttribute('aria-label', ready ? '已登录' : '未登录')
    light.title = ready ? '已登录' : '未登录'
  })
  $('#accountHint').textContent = platformReady() ? `${platformNames[state.platform]}账号已登录` : `此账号尚未登录${platformNames[state.platform]}`
  $('#loginButton').textContent = platformReady() ? '重新登录' : '扫码登录'
  $('#previewAccount').textContent = account.value.trim() || 'main'
}

async function checkHealth() {
  try {
    const result = await api(`/api/health?account=${encodeURIComponent(account.value.trim() || 'main')}`)
    state.accounts = result.accounts || {}
    $('.state-dot').classList.remove('offline')
    $('#systemText').textContent = '本地服务已连接'
    updateAccountUI()
  } catch (error) {
    $('.state-dot').classList.add('offline')
    $('#systemText').textContent = '服务连接失败'
  }
}

function setPlatform(platform) {
  state.platform = platform
  $$('.platform-stamp').forEach((button) => button.classList.toggle('active', button.dataset.platform === platform))
  const xianyu = platform === 'xianyu'
  $('#xianyuFields').hidden = !xianyu
  $('#tagsField').hidden = xianyu
  $('#kindSwitch').hidden = xianyu
  $('#previewPrice').hidden = !xianyu
  if (xianyu) setKind('note')
  $('#title').maxLength = titleLimit()
  updateMediaAccept()
  updateAccountUI()
  updatePreview()
}

function setKind(kind) {
  state.kind = kind
  $$('#kindSwitch button').forEach((button) => button.classList.toggle('active', button.dataset.kind === kind))
  updateMediaAccept()
}

function updateMediaAccept() {
  const video = state.kind === 'video' && state.platform !== 'xianyu'
  mediaInput.accept = video ? 'video/mp4,video/quicktime,video/webm' : 'image/jpeg,image/png,image/webp'
  mediaInput.multiple = !video
  $('#mediaHint').textContent = video ? '选择 1 个视频' : '最多 9 张图片'
  $('#dropHelp').textContent = video ? '支持 MP4、MOV、WEBM' : '支持 JPG、PNG、WEBP'
  const invalid = state.files.some((file) => video ? !file.type.startsWith('video/') : !file.type.startsWith('image/'))
  if (invalid) { clearFiles(); toast('内容类型已变化，请重新选择素材') }
}

function addFiles(files) {
  const wantsVideo = state.kind === 'video' && state.platform !== 'xianyu'
  const selected = [...files].filter((file) => wantsVideo ? file.type.startsWith('video/') : file.type.startsWith('image/'))
  if (!selected.length) return toast(wantsVideo ? '请选择视频文件' : '请选择图片文件', true)
  if (wantsVideo) state.files = selected.slice(0, 1)
  else state.files = [...state.files, ...selected].slice(0, 9)
  renderFiles()
}

function clearFiles() {
  state.files.forEach((file) => file.previewUrl && URL.revokeObjectURL(file.previewUrl))
  state.files = []
  mediaInput.value = ''
  renderFiles()
}

function renderFiles() {
  const list = $('#mediaList')
  const preview = $('#previewMedia')
  list.innerHTML = ''
  preview.innerHTML = ''
  if (!state.files.length) {
    const mediaLabel = state.kind === 'video' && state.platform !== 'xianyu' ? '视频' : '图片'
    preview.innerHTML = `<div class="empty-media"><span>${mediaLabel}</span><small>添加素材后在这里预览</small></div>`
    return
  }
  state.files.forEach((file, index) => {
    file.previewUrl ||= URL.createObjectURL(file)
    const item = document.createElement('div')
    item.className = 'media-item'
    const media = document.createElement(file.type.startsWith('video/') ? 'video' : 'img')
    media.src = file.previewUrl
    if (media.tagName === 'VIDEO') { media.muted = true; media.playsInline = true }
    const remove = document.createElement('button')
    remove.type = 'button'; remove.textContent = '×'; remove.title = `移除 ${file.name}`
    remove.onclick = () => { URL.revokeObjectURL(file.previewUrl); state.files.splice(index, 1); renderFiles() }
    item.append(media, remove); list.append(item)

    const clone = document.createElement(file.type.startsWith('video/') ? 'video' : 'img')
    clone.src = file.previewUrl
    if (clone.tagName === 'VIDEO') { clone.muted = true; clone.controls = true; clone.playsInline = true }
    preview.append(clone)
  })
}

function updatePreview() {
  const title = $('#title').value.trim()
  const body = $('#body').value.trim()
  const count = $('#title').value.length
  $('#titleCount').textContent = `${count} / ${titleLimit()}`
  $('#titleCount').classList.toggle('over-limit', count > titleLimit())
  $('#bodyCount').textContent = `${$('#body').value.length} 字`
  $('#previewTitle').textContent = title || '你的标题会出现在这里'
  $('#previewBody').textContent = body || '正文预览会随着输入实时更新。'
  $('#previewPlatform').textContent = `${platformNames[state.platform]} · 即将发布`
  $('#previewPrice strong').textContent = `¥${$('#price').value || '0'}`
  const tags = $('#tags').value.split(',').map((item) => item.trim().replace(/^#/, '')).filter(Boolean)
  $('#previewTags').innerHTML = tags.map((tag) => `<span>#${escapeHtml(tag)}</span>`).join('')
}

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]))
}

async function pollJob(jobId, onUpdate) {
  clearInterval(state.pollTimer)
  return new Promise((resolve) => {
    const poll = async () => {
      try {
        const job = await api(`/api/jobs/${jobId}`)
        onUpdate(job)
        if (['succeeded', 'failed'].includes(job.status)) { clearInterval(state.pollTimer); resolve(job) }
      } catch (error) { clearInterval(state.pollTimer); resolve({ status: 'failed', message: error.message }) }
    }
    poll()
    state.pollTimer = setInterval(poll, 1000)
  })
}

async function startLogin() {
  const name = account.value.trim() || 'main'
  $('#loginTitle').textContent = `扫码登录${platformNames[state.platform]}`
  $('#loginMessage').textContent = '正在生成二维码，请稍候。'
  $('#qrFrame').innerHTML = '<div class="qr-loading"><i></i><span>正在生成二维码</span></div>'
  loginDialog.showModal()
  const data = new FormData()
  data.append('platform', state.platform); data.append('account', name)
  try {
    const { job_id: jobId } = await api('/api/login', { method: 'POST', body: data })
    const result = await pollJob(jobId, (job) => {
      $('#loginMessage').textContent = job.message
      if (job.qr_code) $('#qrFrame').innerHTML = `<img src="${job.qr_code}" alt="${platformNames[state.platform]}登录二维码">`
      if (job.status === 'succeeded') $('#qrFrame').innerHTML = '<div class="qr-loading"><span style="font-size:42px;color:var(--mint)">✓</span><span>登录成功</span></div>'
    })
    if (result.status === 'succeeded') { await checkHealth(); setTimeout(() => loginDialog.close(), 900); toast(`${platformNames[state.platform]}登录成功`) }
    else toast(result.message || '登录失败', true)
  } catch (error) { $('#loginMessage').textContent = error.message; toast(error.message, true) }
}

async function publish(event) {
  event.preventDefault()
  if (!platformReady()) return toast(`请先登录${platformNames[state.platform]}账号`, true)
  if (!state.files.length) return toast('请添加图片或视频', true)
  if (!$('#title').value.trim() || !$('#body').value.trim()) return toast('请填写标题和正文', true)
  if ($('#title').value.trim().length > titleLimit()) return toast(`${platformNames[state.platform]}标题最多 ${titleLimit()} 个字符`, true)
  if (state.platform === 'xianyu' && (!$('#price').value || !$('#address').value.trim())) return toast('闲鱼商品需要填写价格和所在地', true)

  const data = new FormData()
  data.append('platform', state.platform); data.append('account', account.value.trim() || 'main')
  data.append('kind', state.kind); data.append('title', $('#title').value); data.append('body', $('#body').value)
  data.append('tags', $('#tags').value); data.append('price', $('#price').value); data.append('original_price', $('#originalPrice').value)
  data.append('address', $('#address').value); data.append('shipping_method', $('input[name="shipping"]:checked').value)
  state.files.forEach((file) => data.append('media', file, file.name))

  const card = progressDialog.querySelector('.progress-card')
  card.classList.remove('done', 'failed'); $('#progressClose').hidden = true; $('#resultLink').hidden = true
  $('#progressTitle').textContent = `正在发布到${platformNames[state.platform]}`
  $('#progressMessage').textContent = '正在准备素材…'
  progressDialog.showModal(); $('#publishButton').disabled = true
  try {
    const { job_id: jobId } = await api('/api/publish', { method: 'POST', body: data })
    const result = await pollJob(jobId, (job) => { $('#progressMessage').textContent = job.message })
    const success = result.status === 'succeeded'
    card.classList.add(success ? 'done' : 'failed')
    $('#progressTitle').textContent = success ? '发布完成' : '发布没有完成'
    $('#progressMessage').textContent = result.message
    $('#progressClose').hidden = false
    const url = result.result?.external_url
    if (url) { $('#resultLink').href = url; $('#resultLink').hidden = false }
    toast(success ? '内容已发布' : result.message, !success)
  } catch (error) {
    card.classList.add('failed'); $('#progressTitle').textContent = '发布没有完成'; $('#progressMessage').textContent = error.message; $('#progressClose').hidden = false; toast(error.message, true)
  } finally { $('#publishButton').disabled = false }
}

function clearForm() {
  if (!confirm('清空现在填写的内容？')) return
  form.reset(); clearFiles(); setKind('note'); updatePreview()
}

$$('.platform-stamp').forEach((button) => button.addEventListener('click', () => setPlatform(button.dataset.platform)))
$$('#kindSwitch button').forEach((button) => button.addEventListener('click', () => setKind(button.dataset.kind)))
;['#title', '#body', '#tags', '#price'].forEach((selector) => $(selector).addEventListener('input', updatePreview))
account.addEventListener('change', checkHealth); account.addEventListener('input', updateAccountUI)
$('#loginButton').addEventListener('click', startLogin)
dropzone.addEventListener('click', () => mediaInput.click())
mediaInput.addEventListener('change', () => addFiles(mediaInput.files))
dropzone.addEventListener('dragover', (event) => { event.preventDefault(); dropzone.classList.add('dragging') })
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragging'))
dropzone.addEventListener('drop', (event) => { event.preventDefault(); dropzone.classList.remove('dragging'); addFiles(event.dataTransfer.files) })
form.addEventListener('submit', publish)
$('#clearButton').addEventListener('click', clearForm)
$('#progressClose').addEventListener('click', () => progressDialog.close())
$$('[data-close-modal]').forEach((button) => button.addEventListener('click', () => loginDialog.close()))

setPlatform('xiaohongshu')
checkHealth()
