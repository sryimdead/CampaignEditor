<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '@/api'
import OffersEditor from '@/components/OffersEditor.vue'
import Spinner from '@/components/Spinner.vue'

// Только редактирование существующей кампании. Создание идёт через «Новая кампания».
const props = defineProps({
  id: { type: Number, required: true },
})

const form = reactive({
  name: '',
  alias: '',
  group_id: null,
  traffic_source_id: null,
  state: 'active',
  cost_type: '',
  cost_value: null,
  notes: '',
})

const groups = ref([])
const trafficSources = ref([])
// Офферы кампании (из потока с офферами) и все офферы Keitaro для добавления
const offers = ref([])
const offersTotal = ref(0)
const allOffers = ref([])
const offersError = ref('')
// Текст текущей операции с офферами ('' - ничего не делается). Пока он задан, список заблокирован.
const offersBusyText = ref('')
const offersBusy = computed(() => offersBusyText.value !== '')
const offersSyncing = computed(() => offersBusyText.value === 'sync')
const offersBusyLabel = computed(() => {
  if (offersBusyText.value === 'sync') return 'Синхронизация с Keitaro…'
  return offersBusyText.value || 'Обновление…'
})

const availableOffers = computed(() => {
  const attached = new Set(offers.value.map((o) => o.offer_id))
  return allOffers.value.filter((o) => !attached.has(o.id))
})

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')

function toPayload() {
  const out = {}
  for (const k of ['name', 'alias', 'cost_type', 'notes']) {
    if (form[k] !== '' && form[k] !== null) out[k] = form[k]
  }
  for (const k of ['group_id', 'traffic_source_id']) {
    if (form[k] !== null && form[k] !== '') out[k] = Number(form[k])
  }
  if (form.cost_value !== null && form.cost_value !== '') out.cost_value = Number(form.cost_value)
  out.state = form.state
  return out
}

async function loadCampaign() {
  const [g, t, c] = await Promise.all([
    api.listGroups(),
    api.listTrafficSources(),
    api.getCampaign(props.id),
  ])
  groups.value = g
  trafficSources.value = t
  Object.assign(form, {
    name: c.name ?? '',
    alias: c.alias ?? '',
    group_id: c.group_id ?? null,
    traffic_source_id: c.traffic_source_id ?? null,
    state: c.state ?? 'active',
    cost_type: c.cost_type ?? '',
    cost_value: c.cost_value ?? null,
    notes: c.notes ?? '',
  })
}

function applyOffers(data) {
  offers.value = data.offers
  offersTotal.value = data.total
}

// Выполняет операцию с офферами, показывая спиннер с текстом. Ошибки выводятся над списком.
async function withOffersBusy(text, action) {
  offersError.value = ''
  offersBusyText.value = text
  try {
    await action()
  } catch (e) {
    offersError.value = e.message
  } finally {
    offersBusyText.value = ''
  }
}

// Читает из Keitaro офферы кампании и список всех офферов (для добавления).
async function fetchOffers() {
  const [data, all] = await Promise.all([api.getCampaignOffers(props.id), api.listOffers()])
  applyOffers(data)
  allOffers.value = all
}

// Кнопка «Синхронизировать»: перечитывает офферы кампании из Keitaro.
function syncOffers() {
  return withOffersBusy('sync', fetchOffers)
}

function addOffer(offerId) {
  return withOffersBusy('Добавление оффера…', async () => {
    applyOffers(await api.addCampaignOffer(props.id, offerId))
  })
}

function removeOffer(offerId) {
  return withOffersBusy('Удаление оффера…', async () => {
    applyOffers(await api.removeCampaignOffer(props.id, offerId))
  })
}

// share: число - закрепить, null - снять закрепление, 'invalid' - некорректный ввод
function setWeight(offerId, share) {
  if (share === 'invalid') {
    offersError.value = 'Вес должен быть целым числом от 1 до 100'
    return
  }
  return withOffersBusy('Пересчёт весов…', async () => {
    try {
      applyOffers(await api.setOfferWeight(props.id, offerId, share))
    } catch (e) {
      // Веса не изменились в Keitaro - перечитываем актуальное состояние, но ошибку показываем
      const message = e.message
      await fetchOffers()
      throw new Error(message)
    }
  })
}

async function submit() {
  error.value = ''
  success.value = ''
  if (!form.name.trim()) {
    error.value = 'Введите название кампании'
    return
  }
  saving.value = true
  try {
    await api.updateCampaign(props.id, toPayload())
    success.value = 'Изменения сохранены'
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await loadCampaign()
    await withOffersBusy('Загрузка офферов…', fetchOffers)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="page-header">
    <div>
      <h1>Кампания #{{ id }}</h1>
      <div class="page-subtitle">Редактирование параметров и офферов</div>
    </div>
    <span class="spacer"></span>
    <RouterLink to="/campaigns" class="btn">← К списку</RouterLink>
  </div>

  <section class="card">
    <div class="card-header">
      <h2>Офферы</h2>
      <span class="badge badge-muted">{{ offers.length }}</span>
      <span class="spacer"></span>
      <button type="button" class="btn-sm" :disabled="offersBusy" title="Перечитать офферы из Keitaro" @click="syncOffers">
        <Spinner v-if="offersSyncing" :size="14" label="Синхронизация" />
        <span v-else aria-hidden="true">⟳</span>
        {{ offersSyncing ? 'Синхронизация…' : 'Синхронизировать' }}
      </button>
    </div>
    <OffersEditor
      :rows="offers"
      :total="offersTotal"
      :options="availableOffers"
      :busy="offersBusy"
      :busy-text="offersBusyLabel"
      :error="offersError"
      @add="addOffer"
      @remove="removeOffer"
      @weight="setWeight"
    />
  </section>

  <div v-if="loading" class="loading-block">
    <Spinner />
    <span>Загрузка кампании из Keitaro…</span>
  </div>
  <div v-if="error && !loading && !form.name" class="alert alert-error">{{ error }}</div>

  <form v-else class="card" @submit.prevent="submit">
    <div class="section-title">Параметры кампании</div>
    <div class="form-grid">
      <label class="field">
        <span class="field-label">Название *</span>
        <input v-model="form.name" required maxlength="255" />
      </label>
      <label class="field">
        <span class="field-label">Alias</span>
        <input v-model="form.alias" maxlength="255" />
      </label>
      <label class="field">
        <span class="field-label">Статус</span>
        <select v-model="form.state">
          <option value="active">Активна</option>
          <option value="disabled">Выключена</option>
        </select>
      </label>
      <label class="field">
        <span class="field-label">Группа</span>
        <select v-model="form.group_id">
          <option :value="null">— не выбрано —</option>
          <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
        </select>
      </label>
      <label class="field">
        <span class="field-label">Источник трафика</span>
        <select v-model="form.traffic_source_id">
          <option :value="null">— не выбрано —</option>
          <option v-for="s in trafficSources" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </label>
      <label class="field">
        <span class="field-label">Тип стоимости</span>
        <input v-model="form.cost_type" placeholder="CPC, CPA, CPS…" />
      </label>
      <label class="field">
        <span class="field-label">Стоимость</span>
        <input v-model.number="form.cost_value" type="number" step="0.01" />
      </label>
      <label class="field span-full">
        <span class="field-label">Заметки</span>
        <textarea v-model="form.notes"></textarea>
      </label>
    </div>

    <div class="card-footer">
      <button class="btn-primary" type="submit" :disabled="saving">
        <Spinner v-if="saving" :size="14" label="Сохранение" />
        {{ saving ? 'Сохранение…' : 'Сохранить' }}
      </button>
      <span v-if="success" class="soft" style="color: var(--ok)">{{ success }}</span>
      <span v-if="error" class="error">{{ error }}</span>
    </div>
  </form>
</template>

