<template>
  <t-config-provider :global-config="tdLocale">
    <router-view />
    <t-dialog
      v-model:visible="unauthorizedVisible"
      :header="t('app.sessionExpiredTitle')"
      :body="t('app.sessionExpiredBody')"
      :confirm-btn="{ content: t('app.goLogin'), theme: 'primary' }"
      :close-btn="null"
      @confirm="goLogin"
    />
  </t-config-provider>
</template>

<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearUser } from './store'
import { i18nState, t, tdLocale } from './i18n'
import { updatePageTitle } from './router'

const route = useRoute()
const router = useRouter()
const unauthorizedVisible = ref(false)

watch(
  () => i18nState.locale,
  () => {
    updatePageTitle(route)
  },
)

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
