<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '@/api'
import OffersEditor from '@/components/OffersEditor.vue'
import Spinner from '@/components/Spinner.vue'

const form = reactive({ name: '' })
const selectedGeos = ref([]) // коды стран, в порядке выбора
const countries = ref([])
const countryFilter = ref('')
const defaults = ref(null)
const allOffers = ref([])
const loadingMeta = ref(false)
const submitting = ref(false)
const error = ref('')
const result = ref(null)

// Выбранные офферы (ID, в порядке добавления) и закреплённые веса (offer_id -> процент)
const picked = ref([])
const pins = reactive({})
const preview = ref({ total: 0, offers: [] })
const offersError = ref('')
const offersBusy = ref(false)

const nameOf = (id) => allOffers.value.find((o) => o.id === id)?.name ?? ''

// Строки таблицы: веса приходят с сервера (те же правила, что и для кампании)
const rows = computed(() =>
  preview.value.offers.map((o) => ({ ...o, name: nameOf(o.offer_id) })),
)
const available = computed(() => allOffers.value.filter((o) => !picked.value.includes(o.id)))

const filteredCountries = computed(() => {
  const q = countryFilter.value.trim().toLowerCase()
  if (!q) return countries.value
  return countries.value.filter(
    (c) => c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q),
  )
})

const countryName = (code) => countries.value.find((c) => c.code === code)?.name ?? code

function toggleGeo(code) {
  const i = selectedGeos.value.indexOf(code)
  if (i >= 0) selectedGeos.value.splice(i, 1)
  else selectedGeos.value.push(code)
}

function removeGeo(code) {
  selectedGeos.value = selectedGeos.value.filter((c) => c !== code)
}

// Пересчёт весов на сервере. При ошибке (например, закрепления не оставляют места) откатываем изменение.
async function recalc(rollback) {
  offersError.value = ''
  if (picked.value.length === 0) {
    preview.value = { total: 0, offers: [] }
    return true
  }
  offersBusy.value = true
  try {
    preview.value = await api.previewWeights(picked.value, { ...pins })
    return true
  } catch (e) {
    offersError.value = e.message
    rollback()
    return false
  } finally {
    offersBusy.value = false
  }
}

function addOffer(id) {
  if (picked.value.includes(id)) return
  picked.value.push(id)
  recalc(() => picked.value.splice(picked.value.indexOf(id), 1))
}

function removeOffer(id) {
  const index = picked.value.indexOf(id)
  if (index < 0) return
  const hadPin = id in pins
  const pinValue = pins[id]
  picked.value.splice(index, 1)
  delete pins[id]
  recalc(() => {
    picked.value.splice(index, 0, id)
    if (hadPin) pins[id] = pinValue
  })
}

// share: число - закрепить, null - снять закрепление, 'invalid' - некорректный ввод
function setWeight(id, share) {
  if (share === 'invalid') {
    offersError.value = 'Вес должен быть целым числом от 1 до 100'
    return
  }
  const hadPin = id in pins
  const pinValue = pins[id]
  if (share === null) delete pins[id]
  else pins[id] = share
  recalc(() => {
    if (hadPin) pins[id] = pinValue
    else delete pins[id]
  })
}

async function loadMeta() {
  loadingMeta.value = true
  try {
    const [list, def, offerList] = await Promise.all([
      api.listCountries(),
      api.getCreatorDefaults(),
      api.listOffers(),
    ])
    countries.value = list
    defaults.value = def
    allOffers.value = [...offerList].sort((a, b) => a.name.localeCompare(b.name))
  } catch (e) {
    error.value = e.message
  } finally {
    loadingMeta.value = false
  }
}

async function submit() {
  error.value = ''
  result.value = null
  if (picked.value.length === 0) {
    error.value = 'Добавьте хотя бы один оффер'
    return
  }
  if (selectedGeos.value.length === 0) {
    error.value = 'Выберите хотя бы одну страну'
    return
  }
  submitting.value = true
  try {
    result.value = await api.createCampaignWithOffer({
      name: form.name,
      geos: [...selectedGeos.value],
      offer_ids: [...picked.value],
      weights: { ...pins },
    })
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}

onMounted(loadMeta)
</script>

<template>
  <div class="page-header">
    <div>
      <h1>Новая кампания</h1>
      <div class="page-subtitle">Кампания с офферами и потоками по странам</div>
    </div>
  </div>

  <form class="card" @submit.prevent="submit">
    <div class="section-title">Основное</div>
    <div class="form-grid">
      <label class="field">
        <span class="field-label">Название кампании *</span>
        <input v-model="form.name" required maxlength="255" />
      </label>
    </div>

    <div v-if="defaults" class="alert alert-info defaults">
      Автоматически: домен <strong>{{ defaults.domain }}</strong>, группа
      <strong>{{ defaults.group_name }}</strong>, источник
      <strong>{{ defaults.traffic_source_name }}</strong>
    </div>

    <div class="section-title mt-6">Офферы</div>
    <OffersEditor
      :rows="rows"
      :total="preview.total"
      :options="available"
      :busy="offersBusy || loadingMeta"
      :busy-text="loadingMeta ? 'Загрузка офферов из Keitaro…' : 'Пересчёт весов…'"
      :error="offersError"
      @add="addOffer"
      @remove="removeOffer"
      @weight="setWeight"
    />

    <div class="section-title mt-6">Страны</div>
    <div class="stack">
      <div class="row">
        <span class="soft">Выбранные страны уйдут на google.com, все остальные — на офферы кампании.</span>
        <span class="spacer"></span>
        <span class="badge badge-muted">Выбрано: {{ selectedGeos.length }}</span>
      </div>

      <div v-if="selectedGeos.length" class="chips">
        <button
          v-for="code in selectedGeos"
          :key="code"
          type="button"
          class="chip"
          :title="'Убрать ' + countryName(code)"
          @click="removeGeo(code)"
        >
          {{ code }} · {{ countryName(code) }} ✕
        </button>
      </div>

      <input v-model="countryFilter" type="search" placeholder="Поиск по коду или названию" style="max-width: 360px" />

      <div v-if="loadingMeta" class="loading-block">
        <Spinner />
        <span>Загрузка списка стран…</span>
      </div>
      <div v-else class="check-list">
        <label v-for="c in filteredCountries" :key="c.code" class="check-item">
          <input type="checkbox" :checked="selectedGeos.includes(c.code)" @change="toggleGeo(c.code)" />
          <span class="code">{{ c.code }}</span>
          <span>{{ c.name }}</span>
        </label>
        <div v-if="!filteredCountries.length" class="muted" style="padding: 8px">Ничего не найдено</div>
      </div>
    </div>

    <div class="card-footer">
      <button class="btn-primary" type="submit" :disabled="submitting || loadingMeta">
        <Spinner v-if="submitting" :size="14" label="Создание кампании" />
        {{ submitting ? 'Создание кампании…' : 'Создать кампанию' }}
      </button>
      <span v-if="error" class="error">{{ error }}</span>
    </div>
  </form>

  <div v-if="result" class="alert alert-success result">
    <span>Кампания #{{ result.campaign.id }} создана, потоков: {{ result.streams.length }}.</span>
    <RouterLink :to="`/campaigns/${result.campaign.id}/edit`">Открыть кампанию →</RouterLink>
  </div>
</template>

<style scoped>
.defaults { margin-top: 16px; }
.result { justify-content: space-between; align-items: center; flex-wrap: wrap; }
</style>
