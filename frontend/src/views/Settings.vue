<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">个人设置</h2>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; max-width: 980px">
      <div class="panel">
        <h3 style="margin: 0 0 16px; font-size: 16px">账号信息</h3>
        <t-form label-width="90px">
          <t-form-item label="用户名">{{ user?.username }}</t-form-item>
          <t-form-item label="显示名">
            <t-input v-model="profile.display_name" :maxlength="64" placeholder="留空则显示用户名" />
          </t-form-item>
          <t-form-item label="邮箱">
            <t-input v-model="profile.email" placeholder="选填，仅作备注，不参与登录" />
          </t-form-item>
          <t-form-item label="角色">
            <t-tag :theme="user?.is_admin ? 'primary' : 'default'" variant="light" size="small">
              {{ user?.is_admin ? '管理员' : '普通用户' }}
            </t-tag>
          </t-form-item>
          <t-form-item label="状态">
            <t-tag :theme="user?.is_active ? 'success' : 'default'" variant="light" size="small">
              {{ user?.is_active ? '启用' : '停用' }}
            </t-tag>
          </t-form-item>
          <t-form-item label=" ">
            <t-button theme="primary" :loading="savingProfile" @click="saveProfile">保存资料</t-button>
          </t-form-item>
        </t-form>
      </div>

      <div class="panel">
        <h3 style="margin: 0 0 16px; font-size: 16px">修改密码</h3>
        <t-form label-width="90px" :data="form" @submit="submit">
          <t-form-item label="当前密码">
            <t-input v-model="form.old" type="password" placeholder="请输入当前密码" />
          </t-form-item>
          <t-form-item label="新密码">
            <t-input v-model="form.password" type="password" placeholder="至少 6 位" />
          </t-form-item>
          <t-form-item label="确认密码">
            <t-input v-model="form.confirm" type="password" placeholder="再次输入新密码" />
          </t-form-item>
          <t-form-item label=" ">
            <t-button theme="primary" type="submit" :loading="saving">保存</t-button>
          </t-form-item>
        </t-form>
      </div>
    </div>

    <div v-if="user?.is_admin" class="panel" style="margin-top: 16px; max-width: 980px">
      <h3 style="margin: 0 0 6px; font-size: 16px">系统设置</h3>
      <div class="muted" style="margin-bottom: 16px">仅管理员可见，修改后立即生效</div>
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 24px">
        <div>
          <div style="font-weight: 500">允许用户自助注册</div>
          <div class="muted" style="margin-top: 4px">
            开启后，登录页可自助注册普通账号；关闭后仅管理员能在「用户」页添加账号。
          </div>
        </div>
        <t-switch
          v-model="settings.allow_registration"
          :loading="savingSetting"
          @change="saveSetting"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'
import { setUser, store } from '../store'

const user = computed(() => store.user)
const saving = ref(false)
const savingProfile = ref(false)
const profile = reactive({ display_name: '', email: '' })
const form = reactive({ old: '', password: '', confirm: '' })
const settings = reactive({ allow_registration: true })
const savingSetting = ref(false)

async function loadSettings() {
  if (!user.value?.is_admin) return
  try {
    const data = await api.getSettings()
    settings.allow_registration = !!data.allow_registration
  } catch (e) {
    /* 忽略：普通用户或未登录 */
  }
}

async function saveSetting(value) {
  savingSetting.value = true
  try {
    await api.updateSettings({ allow_registration: !!value })
    MessagePlugin.success(value ? '已开启用户注册' : '已关闭用户注册')
  } catch (e) {
    MessagePlugin.error(e.message || '保存失败')
    await loadSettings()
  } finally {
    savingSetting.value = false
  }
}

function syncProfile() {
  profile.display_name = user.value?.display_name || ''
  profile.email = user.value?.email || ''
}

async function saveProfile() {
  const email = (profile.email || '').trim()
  if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    MessagePlugin.warning('邮箱格式不正确')
    return
  }
  savingProfile.value = true
  try {
    const data = await api.updateProfile({
      display_name: (profile.display_name || '').trim(),
      email,
    })
    if (data?.user) setUser(data.user)
    MessagePlugin.success('资料已保存')
  } catch (e) {
    MessagePlugin.error(e.message || '保存失败')
  } finally {
    savingProfile.value = false
  }
}

onMounted(() => {
  syncProfile()
  loadSettings()
})

async function submit() {
  if (!form.old || !form.password) {
    MessagePlugin.warning('请填写完整')
    return
  }
  if (form.password.length < 6) {
    MessagePlugin.warning('新密码至少 6 位')
    return
  }
  if (form.password !== form.confirm) {
    MessagePlugin.warning('两次输入的密码不一致')
    return
  }
  saving.value = true
  try {
    await api.changePassword(form.old, form.password)
    MessagePlugin.success('密码已修改')
    form.old = ''
    form.password = ''
    form.confirm = ''
  } catch (e) {
    MessagePlugin.error(e.message || '修改失败')
  } finally {
    saving.value = false
  }
}
</script>
