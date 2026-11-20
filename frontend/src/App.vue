<template>
  <router-view />
  <t-dialog
    v-model:visible="unauthorizedVisible"
    header="登录已失效"
    body="当前会话已过期，请重新登录。"
    :confirm-btn="{ content: '去登录', theme: 'primary' }"
    :close-btn="null"
    @confirm="goLogin"
  />
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { clearUser } from './store'

const router = useRouter()
const unauthorizedVisible = ref(false)

function onUnauthorized() {
  clearUser()
  if (router.currentRoute.value.name !== 'login') unauthorizedVisible.value = true
}

function goLogin() {
  unauthorizedVisible.value = false
  router.replace({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
}

onMounted(() => window.addEventListener('console:unauthorized', onUnauthorized))
onUnmounted(() => window.removeEventListener('console:unauthorized', onUnauthorized))
</script>
