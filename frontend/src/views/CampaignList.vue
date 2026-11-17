<script setup>
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '@/api'
import Spinner from '@/components/Spinner.vue'

const campaigns = ref([])
const loading = ref(false)
const error = ref('')
const busyId = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    campaigns.value = await api.listCampaigns()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function toggleState(c) {
  busyId.value = c.id
  error.value = ''
  const next = c.state === 'active' ? 'disabled' : 'active'
  try {
    await api.updateCampaign(c.id, { state: next })
    c.state = next
  } catch (e) {
    error.value = e.message
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="page-header">
    <div>
      <h1>Кампании</h1>
      <div class="page-subtitle">Кампании из Keitaro</div>
    </div>
    <span class="spacer"></span>
    <button type="button" :disabled="loading" @click="load">
      <Spinner v-if="loading" :size="14" label="Обновление" />
      {{ loading ? 'Обновление…' : 'Обновить' }}
    </button>
    <RouterLink to="/create" class="btn btn-primary">+ Новая кампания</RouterLink>
  </div>

  <div v-if="error" class="alert alert-error">{{ error }}</div>

  <section class="card">
    <div v-if="loading && !campaigns.length" class="loading-block">
      <Spinner />
      <span>Загрузка кампаний из Keitaro…</span>
    </div>
    <div v-else class="table-wrap">
      <table v-if="campaigns.length">
        <thead>
          <tr>
            <th class="num">ID</th>
            <th>Название</th>
            <th>Статус</th>
            <th class="hide-sm">Группа</th>
            <th class="hide-sm">Источник</th>
            <th class="actions">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in campaigns" :key="c.id">
            <td class="num muted">{{ c.id }}</td>
            <td>{{ c.name }}</td>
            <td>
              <span class="badge" :class="c.state === 'active' ? 'badge-ok' : 'badge-muted'">
                {{ c.state === 'active' ? 'Активна' : 'Выключена' }}
              </span>
            </td>
            <td class="hide-sm muted">{{ c.group_id ?? '—' }}</td>
            <td class="hide-sm muted">{{ c.traffic_source_id ?? '—' }}</td>
            <td class="actions">
              <button
                type="button"
                class="btn-sm"
                :disabled="busyId === c.id"
                @click="toggleState(c)"
              >
                <Spinner v-if="busyId === c.id" :size="12" label="Сохранение" />
                {{ c.state === 'active' ? 'Выключить' : 'Включить' }}
              </button>
              <RouterLink :to="`/campaigns/${c.id}/edit`" class="btn btn-ghost btn-sm">
                Изменить
              </RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="!loading && !error" class="empty-state">Кампаний пока нет.</p>
    </div>
  </section>
</template>
