<template>
  <div class="login-wrap">
    <div class="login-card">
      <img class="login-logo" :src="logo" alt="RustDesk" />
      <h1 class="login-title">{{ title }}</h1>
      <p class="login-sub">{{ subtitle }}</p>
      <t-form :data="form" label-width="0" :show-error-message="false" @submit="submit">
        <t-form-item name="username">
          <t-input v-model="form.username" size="large" placeholder="用户名" clearable autofocus />
        </t-form-item>
        <t-form-item name="password">
          <t-input v-model="form.password" type="password" size="large" placeholder="密码" @enter="submit" />
        </t-form-item>
        <t-form-item v-if="setupMode || registerMode" name="confirm">
          <t-input v-model="form.confirm" type="password" size="large" placeholder="确认密码" @enter="submit" />
        </t-form-item>
        <t-button theme="primary" type="submit" size="large" block :loading="loading">
          {{ submitText }}
        </t-button>
      </t-form>
      <div v-if="!setupMode" class="login-switch">
        <a v-if="!registerMode && allowRegistration" class="login-link" @click="switchMode(true)">没有账号？注册</a>
        <a v-else-if="registerMode" class="login-link" @click="switchMode(false)">已有账号？返回登录</a>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'
import logo from '../assets/logo-128.png'
import { setUser } from '../store'

const router = useRouter()
const route = useRoute()
const form = reactive({ username: '', password: '', confirm: '' })
const loading = ref(false)
const setupMode = ref(false)
const registerMode = ref(false)
const allowRegistration = ref(false)

const title = computed(() => (setupMode.value ? '初始化控制台' : registerMode.value ? '注册账号' : 'RustDesk 控制台'))
const subtitle = computed(() => {
  if (setupMode.value) return '首次使用，请创建第一个管理员账号'
  if (registerMode.value) return '注册后即可登录控制台（权限由管理员分配）'
  return '使用管理员或普通用户账号登录'
})
const submitText = computed(() => (setupMode.value ? '创建管理员' : registerMode.value ? '注 册' : '登 录'))

function switchMode(toRegister) {
  registerMode.value = toRegister
  form.password = ''
  form.confirm = ''
}

function goNext() {
  const redirect = route.query.redirect
  router.replace(typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/dashboard')
}

async function submit() {
  if (!form.username || !form.password) {
    MessagePlugin.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    if (setupMode.value) {
      if (form.password.length < 6) {
        MessagePlugin.warning('密码至少 6 位')
        return
      }
      if (form.password !== form.confirm) {
        MessagePlugin.warning('两次输入的密码不一致')
        return
      }
      const data = await api.setup({ username: form.username.trim(), password: form.password })
      setUser(data.user)
      MessagePlugin.success('管理员已创建')
      goNext()
      return
    }
    if (registerMode.value) {
      if (form.password.length < 8) {
        MessagePlugin.warning('密码至少 8 位')
        return
      }
      if (form.password !== form.confirm) {
        MessagePlugin.warning('两次输入的密码不一致')
        return
      }
      await api.register({ username: form.username.trim(), password: form.password })
      MessagePlugin.success('注册成功，请登录')
      switchMode(false)
      return
    }
    const data = await api.login(form.username.trim(), form.password)
    setUser(data.user)
    MessagePlugin.success('登录成功')
    goNext()
  } catch (e) {
    MessagePlugin.error(e.message || '操作失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const data = await api.setupStatus()
    setupMode.value = !!data.needs_setup
    allowRegistration.value = !!data.allow_registration
  } catch (e) {
    /* 忽略：按登录处理 */
  }
})
</script>

<style scoped>
.login-card :deep(.t-form__item) {
  display: block;
  margin-bottom: 16px !important;
}

.login-card :deep(.t-form__label) {
  display: none;
}

.login-card :deep(.t-form__controls) {
  flex: 1;
  margin-left: 0 !important;
}

.login-card :deep(.t-form__controls-content) {
  width: 100%;
}

.login-card :deep(.t-input__wrap) {
  width: 100%;
}
</style>
