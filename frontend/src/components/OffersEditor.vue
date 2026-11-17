<script setup>
import { computed } from 'vue'
import OfferCombobox from '@/components/OfferCombobox.vue'
import Spinner from '@/components/Spinner.vue'

// Общий редактор списка офферов: используется и в создателе, и в редакторе кампании.
// Сам ничего не запрашивает: данные приходят из родителя, действия уходят событиями.
const props = defineProps({
  rows: { type: Array, required: true }, // [{ offer_id, name, share, pinned }]
  total: { type: Number, default: 0 },
  options: { type: Array, required: true }, // офферы для добавления: [{ id, name }]
  busy: { type: Boolean, default: false },
  busyText: { type: String, default: 'Обновление…' },
  error: { type: String, default: '' },
  addPlaceholder: { type: String, default: 'Начните вводить название или ID' },
})
const emit = defineEmits(['add', 'remove', 'weight'])

const newOfferId = computed({
  get: () => null,
  set: (id) => {
    if (id) emit('add', id)
  },
})

function onWeightChange(row, raw) {
  if (raw === '' || raw === null) return
  const value = Number(raw)
  if (!Number.isInteger(value) || value < 1 || value > 100) {
    emit('weight', row.offer_id, 'invalid')
    return
  }
  emit('weight', row.offer_id, value)
}
</script>

<template>
  <div>
    <div v-if="error" class="alert alert-error mb-2">{{ error }}</div>

    <div class="table-wrap busy-host">
      <div v-if="busy" class="busy-overlay" role="status">
        <Spinner />
        <span>{{ busyText }}</span>
      </div>
      <table v-if="rows.length">
        <thead>
          <tr>
            <th class="num">ID</th>
            <th>Название</th>
            <th>Вес</th>
            <th class="actions">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in rows" :key="o.offer_id">
            <td class="num muted">{{ o.offer_id }}</td>
            <td>{{ o.name || '—' }}</td>
            <td>
              <div class="row weight-row">
                <input
                  type="number"
                  min="1"
                  max="100"
                  step="1"
                  class="weight-input"
                  :value="o.share"
                  :disabled="busy"
                  :title="o.pinned ? 'Вес закреплён' : 'Вес рассчитан автоматически. Введите значение, чтобы закрепить'"
                  @change="onWeightChange(o, $event.target.value)"
                />
                <span class="soft">%</span>
                <span v-if="o.pinned" class="badge badge-accent">закреплён</span>
              </div>
            </td>
            <td class="actions">
              <button
                v-if="o.pinned"
                type="button"
                class="btn-sm"
                :disabled="busy"
                title="Вернуть автоматический расчёт веса"
                @click="emit('weight', o.offer_id, null)"
              >
                Авто
              </button>
              <button
                type="button"
                class="btn-danger btn-sm"
                :disabled="busy || rows.length <= 1"
                :title="rows.length <= 1 ? 'Нельзя удалить последний оффер' : 'Удалить оффер'"
                @click="emit('remove', o.offer_id)"
              >
                Удалить
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="!busy" class="empty-state">Офферы не выбраны.</p>
      <div v-else class="loading-block" style="min-height: 96px"></div>
    </div>

    <div v-if="rows.length" class="total-line" :class="{ bad: total !== 100 }">
      <span>Итого</span>
      <strong>{{ total }}%</strong>
      <span v-if="total !== 100" class="total-hint">должно быть 100%</span>
    </div>

    <div class="field add-field">
      <span class="field-label">Добавить оффер</span>
      <OfferCombobox
        v-model="newOfferId"
        :options="options"
        :loading="busy"
        :placeholder="addPlaceholder"
      />
    </div>
  </div>
</template>

<style scoped>
.weight-row { flex-wrap: nowrap; gap: 8px; }
.weight-input { width: 84px; height: 30px; }
.total-line {
  display: flex;
  align-items: baseline;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
  padding: 10px 16px;
  background: var(--surface-muted);
  border-radius: var(--radius-sm);
}
.total-line strong { font-size: 1.05rem; }
.total-line.bad strong { color: var(--danger); }
.total-hint { color: var(--danger); font-size: 0.88rem; }
.add-field { margin-top: 16px; }
</style>
