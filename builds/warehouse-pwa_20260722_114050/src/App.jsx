import { useEffect, useState } from 'react'
import { apiClient } from './api/client'
import InventoryExcelPage from './InventoryExcelPage'

const pages = {
  home: 'داشبورد',
  inventory: 'موجودی انبار',
  inventoryExcel: 'ورود موجودی با Excel',
  users: 'مدیریت کاربران',
  transfer: 'ثبت حواله انتقال',
  approvals: 'کارتابل حواله‌ها',
  disputes: 'مغایرت  و تیکت',
  production: 'تولید و فرمولاسیون',
  packaging: 'بسته‌بندی و خسارت',
}

function PageHeader({ title, onBack }) {
  return (
    <div className="page-header">
      <button className="ghost-button" onClick={onBack}>
        بازگشت
      </button>
      <h2>{title}</h2>
    </div>
  )
}

function PlaceholderPage({ title, description, onBack }) {
  return (
    <>
      <PageHeader title={title} onBack={onBack} />

      <section className="welcome-card">
        <h2>{title}</h2>
        <p>{description}</p>
      </section>
    </>
  )
}

function formatNumber(value) {
  if (value === null || value === undefined) return '-'
  return Number(value).toLocaleString('fa-IR')
}

function formatTehranDate(value) {
  if (!value) return '-'
  const raw = String(value).trim().replace(' ', 'T')
  const date = new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(raw) ? raw : `${raw}Z`)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('fa-IR', {
    timeZone: 'Asia/Tehran', dateStyle: 'short', timeStyle: 'medium'
  }).format(date)
}
function InventoryPage({ user, onBack }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  useEffect(() => {
    const loadInventory = async () => {
      setLoading(true)
      setError('')

      try {
        const response = await apiClient.get('/reports/warehouse-inventory-status')
        let data = response.data || []

        if (user.role === 'warehouse_manager' && user.warehouse_id) {
          data = data.filter((item) => item.warehouse_id === user.warehouse_id)
        }

        setItems(data)
      } catch (err) {
        const detail = err?.response?.data?.detail
        setError(detail || 'خطا در دریافت موجودی انبار')
      } finally {
        setLoading(false)
      }
    }

    loadInventory()
  }, [user])

  const filteredItems = items.filter((item) => {
    const keyword = search.trim().toLowerCase()

    if (!keyword) return true

    return (
      String(item.product || '').toLowerCase().includes(keyword) ||
      String(item.warehouse || '').toLowerCase().includes(keyword) ||
      String(item.batch_number || '').toLowerCase().includes(keyword) ||
      String(item.product_id || '').includes(keyword) ||
      String(item.batch_id || '').includes(keyword)
    )
  })

  return (
    <>
      <PageHeader title="موجودی انبار" onBack={onBack} />

      <section className="inventory-toolbar">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="جستجو بر اساس کالا، انبار یا بچ..."
        />
      </section>

      {loading && (
        <section className="welcome-card">
          <p>در حال دریافت موجودی...</p>
        </section>
      )}

      {error && (
        <section className="error-box">
          {error}
        </section>
      )}

      {!loading && !error && (
        <>
          <section className="summary-row">
            <div className="summary-card">
              <span>تعداد ردیف‌ها</span>
              <strong>{formatNumber(filteredItems.length)}</strong>
            </div>

            <div className="summary-card">
              <span>مجموع موجودی آزاد</span>
              <strong>
                {formatNumber(
                  filteredItems.reduce((sum, item) => sum + Number(item.free_quantity || 0), 0)
                )}
              </strong>
            </div>
          </section>

          <section className="inventory-list">
            {filteredItems.length === 0 ? (
              <div className="empty-state">
                موردی برای نمایش وجود ندارد.
              </div>
            ) : (
              filteredItems.map((item) => (
                <article
                  className="inventory-item"
                  key={`${item.warehouse_id}-${item.product_id}-${item.batch_id}`}
                >
                  <div className="inventory-item-header">
                    <h3>{item.product}</h3>
                    <span>کالا #{item.product_id}</span>
                  </div>

                  <div className="inventory-meta">
                    <span>{item.warehouse}</span>
                    <span>بچ: {item.batch_number}</span>
                  </div>

                  <div className="quantity-grid">
                    <div>
                      <span>کل</span>
                      <strong>{formatNumber(item.quantity)}</strong>
                    </div>

                    <div>
                      <span>رزرو</span>
                      <strong>{formatNumber(item.reserved_quantity)}</strong>
                    </div>

                    <div>
                      <span>آزاد</span>
                      <strong>{formatNumber(item.free_quantity)}</strong>
                    </div>
                  </div>
                </article>
              ))
            )}
          </section>
        </>
      )}
    </>
  )
}

function TransferPage({ user, onBack }) {
  const [inventoryItems, setInventoryItems] = useState([])
  const [destinations, setDestinations] = useState([])

  const [sourceWarehouseId, setSourceWarehouseId] = useState(
    user.role === 'warehouse_manager' && user.warehouse_id ? String(user.warehouse_id) : ''
  )
  const [selectedInventoryKey, setSelectedInventoryKey] = useState('')
  const [receiverWarehouseId, setReceiverWarehouseId] = useState('')
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')

  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(null)

  const [packagingPreview, setPackagingPreview] = useState(null)
  const [packagingPreviewLoading, setPackagingPreviewLoading] = useState(false)
  const [packagingPreviewError, setPackagingPreviewError] = useState('')

  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      setError('')

      try {
        const [inventoryResponse, destinationsResponse] = await Promise.all([
          apiClient.get('/reports/warehouse-inventory-status'),
          apiClient.get('/warehouses/destinations'),
        ])

        let inventoryData = inventoryResponse.data || []
        let destinationData = destinationsResponse.data || []

        inventoryData = inventoryData.filter((item) => Number(item.free_quantity || 0) > 0)

        if (user.role === 'warehouse_manager' && user.warehouse_id) {
          inventoryData = inventoryData.filter((item) => item.warehouse_id === user.warehouse_id)
          destinationData = destinationData.filter((item) => item.id !== user.warehouse_id)
        }

        setInventoryItems(inventoryData)
        setDestinations(destinationData)

        if (user.role === 'warehouse_manager' && user.warehouse_id) {
          setSourceWarehouseId(String(user.warehouse_id))
        }
      } catch (err) {
        const detail = err?.response?.data?.detail
        setError(detail || 'خطا در دریافت اطلاعات حواله')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [user])

  const sourceWarehouses = Array.from(
    new Map(
      inventoryItems.map((item) => [
        item.warehouse_id,
        {
          id: item.warehouse_id,
          name: item.warehouse,
        },
      ])
    ).values()
  )

  const availableItems = inventoryItems.filter((item) => {
    if (!sourceWarehouseId) return false
    return item.warehouse_id === Number(sourceWarehouseId)
  })

  const selectedItem = availableItems.find((item) => {
    const key = `${item.warehouse_id}-${item.product_id}-${item.batch_id}`
    return key === selectedInventoryKey
  })

  useEffect(() => {
    setPackagingPreview(null)
    setPackagingPreviewError('')

    const transferAmount = Number(amount)

    if (
      !sourceWarehouseId ||
      !selectedItem ||
      !Number.isFinite(transferAmount) ||
      transferAmount <= 0
    ) {
      setPackagingPreviewLoading(false)
      return undefined
    }

    let cancelled = false

    const timer = window.setTimeout(async () => {
      setPackagingPreviewLoading(true)

      try {
        const response = await apiClient.post(
          '/transfers/packaging-preview',
          {
            sender_warehouse_id: Number(sourceWarehouseId),
            product_id: selectedItem.product_id,
            amount: transferAmount,
          }
        )

        if (!cancelled) {
          setPackagingPreview(response.data)
        }
      } catch (err) {
        if (!cancelled) {
          const detail = err?.response?.data?.detail

          setPackagingPreviewError(
            typeof detail === 'string'
              ? detail
              : detail?.message || 'خطا در دریافت پیش‌نمایش بسته‌بندی'
          )
        }
      } finally {
        if (!cancelled) {
          setPackagingPreviewLoading(false)
        }
      }
    }, 350)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [sourceWarehouseId, selectedInventoryKey, amount])

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setSuccess(null)

    if (!sourceWarehouseId) {
      setError('انبار مبدأ را انتخاب کنید.')
      return
    }

    if (!receiverWarehouseId) {
      setError('انبار مقصد را انتخاب کنید.')
      return
    }

    if (!selectedItem) {
      setError('کالا و بچ را انتخاب کنید.')
      return
    }

    const transferAmount = Number(amount)

    if (!transferAmount || transferAmount <= 0) {
      setError('تعداد حواله باید بزرگتر از صفر باشد.')
      return
    }

    if (transferAmount > Number(selectedItem.free_quantity || 0)) {
      setError(`موجودی آزاد کافی نیست. موجودی آزاد: ${formatNumber(selectedItem.free_quantity)}`)
      return
    }

    setSubmitting(true)

    try {
      const payload = {
        sender_warehouse_id: Number(sourceWarehouseId),
        receiver_warehouse_id: Number(receiverWarehouseId),
        product_id: selectedItem.product_id,
        batch_id: selectedItem.batch_id,
        amount: transferAmount,
        description: description || null,
      }

      const previewResponse = await apiClient.post(
        '/transfers/packaging-preview',
        {
          sender_warehouse_id: Number(sourceWarehouseId),
          product_id: selectedItem.product_id,
          amount: transferAmount,
        }
      )

      const currentPreview = previewResponse.data
      setPackagingPreview(currentPreview)
      setPackagingPreviewError('')

      if (
        currentPreview.packaging_required &&
        !currentPreview.all_dispatch_items_available
      ) {
        setError(
          'موجودی بسته‌بندی مرحله ارسال برای ثبت این حواله کافی نیست.'
        )
        return
      }

      const response = await apiClient.post('/transfers/', payload)

      setSuccess(response.data)
      setAmount('')
      setDescription('')
      setSelectedInventoryKey('')
      setPackagingPreview(null)
      setPackagingPreviewError('')

      const inventoryResponse = await apiClient.get('/reports/warehouse-inventory-status')
      let inventoryData = inventoryResponse.data || []
      inventoryData = inventoryData.filter((item) => Number(item.free_quantity || 0) > 0)

      if (user.role === 'warehouse_manager' && user.warehouse_id) {
        inventoryData = inventoryData.filter((item) => item.warehouse_id === user.warehouse_id)
      }

      setInventoryItems(inventoryData)
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(detail || 'خطا در ثبت حواله انتقال')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <PageHeader title="ثبت حواله انتقال" onBack={onBack} />

      {loading && (
        <section className="welcome-card">
          <p>در حال دریافت اطلاعات...</p>
        </section>
      )}

      {error && (
        <section className="error-box transfer-message">
          {error}
        </section>
      )}

      {success && (
        <section className="success-box transfer-message">
          <strong>حواله با موفقیت ثبت شد.</strong>
          <span>شماره حواله: {success.transfer_id || '-'}</span>
          <span>وضعیت: {success.transfer_status || '-'}</span>
          {success.message && <span>{success.message}</span>}
        </section>
      )}

      {!loading && (
        <form className="transfer-form" onSubmit={handleSubmit}>
          <label>
            انبار مبدأ
            <select
              value={sourceWarehouseId}
              onChange={(event) => {
                setSourceWarehouseId(event.target.value)
                setSelectedInventoryKey('')
              }}
              disabled={user.role === 'warehouse_manager'}
              required
            >
              <option value="">انتخاب انبار مبدأ</option>
              {sourceWarehouses.map((warehouse) => (
                <option key={warehouse.id} value={warehouse.id}>
                  {warehouse.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            انبار مقصد
            <select
              value={receiverWarehouseId}
              onChange={(event) => setReceiverWarehouseId(event.target.value)}
              required
            >
              <option value="">انتخاب انبار مقصد</option>
              {destinations
                .filter((warehouse) => String(warehouse.id) !== String(sourceWarehouseId))
                .map((warehouse) => (
                  <option key={warehouse.id} value={warehouse.id}>
                    {warehouse.name}
                    {warehouse.location ? ` - ${warehouse.location}` : ''}
                  </option>
                ))}
            </select>
          </label>

          <label>
            کالا و بچ
            <select
              value={selectedInventoryKey}
              onChange={(event) => setSelectedInventoryKey(event.target.value)}
              required
            >
              <option value="">انتخاب کالا از موجودی آزاد</option>
              {availableItems.map((item) => {
                const key = `${item.warehouse_id}-${item.product_id}-${item.batch_id}`

                return (
                  <option key={key} value={key}>
                    {item.product} | بچ {item.batch_number} | آزاد: {formatNumber(item.free_quantity)}
                  </option>
                )
              })}
            </select>
          </label>

          {selectedItem && (
            <section className="selected-stock-card">
              <h3>{selectedItem.product}</h3>
              <p>انبار: {selectedItem.warehouse}</p>
              <p>بچ: {selectedItem.batch_number}</p>

              <div className="quantity-grid">
                <div>
                  <span>کل</span>
                  <strong>{formatNumber(selectedItem.quantity)}</strong>
                </div>

                <div>
                  <span>رزرو</span>
                  <strong>{formatNumber(selectedItem.reserved_quantity)}</strong>
                </div>

                <div>
                  <span>آزاد</span>
                  <strong>{formatNumber(selectedItem.free_quantity)}</strong>
                </div>
              </div>
            </section>
          )}

          <label>
            مقدار انتقال
            <input
              type="number"
              min="0"
              step="0.01"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="مثلاً 10"
              required
            />
          </label>

          {/* PACKAGING_PREVIEW_UI_START */}
          {packagingPreviewLoading && (
            <section className="selected-stock-card">
              <p>در حال دریافت پیش‌نمایش بسته‌بندی...</p>
            </section>
          )}

          {packagingPreviewError && (
            <section className="error-box transfer-message">
              {packagingPreviewError}
            </section>
          )}

          {packagingPreview && !packagingPreview.packaging_required && (
            <section className="selected-stock-card">
              <h3>بسته‌بندی نیاز نیست</h3>
              <p>این کالا برای حواله به بسته‌بندی اضافی نیاز ندارد.</p>
            </section>
          )}

          {packagingPreview?.packaging_required && (
            <section className="selected-stock-card">
              <h3>پیش‌نمایش بسته‌بندی</h3>

              <p>
                پروفایل: {packagingPreview.profile_name}
                {' | '}
                نسخه {formatNumber(packagingPreview.profile_version)}
              </p>

              <div className="inventory-list">
                {packagingPreview.items.map((item) => (
                  <article
                    className="inventory-item"
                    key={item.profile_item_id}
                  >
                    <div className="inventory-item-header">
                      <h3>{item.material_name}</h3>
                      <span>{item.material_sku}</span>
                    </div>

                    <div className="transfer-detail-grid">
                      <div>
                        <span>مرحله مصرف</span>
                        <strong>
                          {item.consumption_stage === 'production'
                            ? 'مصرف‌شده هنگام تولید'
                            : 'موردنیاز هنگام ارسال'}
                        </strong>
                      </div>

                      <div>
                        <span>مقدار لازم</span>
                        <strong>
                          {formatNumber(item.required_quantity)}
                        </strong>
                      </div>

                      {item.consumption_stage === 'dispatch' && (
                        <>
                          <div>
                            <span>موجودی آزاد</span>
                            <strong>
                              {formatNumber(item.available_quantity)}
                            </strong>
                          </div>

                          <div>
                            <span>وضعیت</span>
                            <strong>
                              {item.sufficient
                                ? 'موجودی کافی'
                                : 'کمبود موجودی'}
                            </strong>
                          </div>
                        </>
                      )}
                    </div>
                  </article>
                ))}
              </div>

              {!packagingPreview.all_dispatch_items_available && (
                <div className="error-box transfer-message">
                  موجودی یک یا چند قلم بسته‌بندی مرحله ارسال کافی
                  نیست؛ ثبت حواله ممکن نیست.
                </div>
              )}
            </section>
          )}
          {/* PACKAGING_PREVIEW_UI_END */}

          <label>
            توضیحات
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="توضیحات اختیاری حواله"
              rows="3"
            />
          </label>

          <button type="submit" disabled={submitting}>
            {submitting ? 'در حال ثبت حواله...' : 'ثبت حواله انتقال'}
          </button>
        </form>
      )}
    </>
  )
}

function statusLabel(status) {
  const labels = {
    pending_source_approval: 'در انتظار تایید مبدأ',
    pending_destination: 'در انتظار تایید مقصد',
    disputed: 'دارای مغایرت',
    confirmed: 'تایید نهایی شده',
    rejected: 'رد شده',
    expired: 'منقضی شده',
  }

  return labels[status] || status || '-'
}

function roleLabel(role) {
  if (role === 'sender') return 'مبدأ'
  if (role === 'receiver') return 'مقصد'
  return role || '-'
}

function packagingStageLabel(stage) {
  if (stage === 'production') {
    return 'مصرف‌شده هنگام تولید'
  }

  if (stage === 'dispatch') {
    return 'موردنیاز هنگام ارسال'
  }

  return stage || '-'
}

function packagingStatusLabel(status) {
  const labels = {
    planned: 'برنامه‌ریزی‌شده',
    reserved: 'رزروشده',
    issued: 'صادرشده',
    received: 'دریافت‌شده',
    disputed: 'دارای مغایرت',
    released: 'آزادشده',
  }

  return labels[status] || status || '-'
}


function ApprovalsPage({ user, onBack }) {
  const [warehouses, setWarehouses] = useState([])
  const [selectedWarehouseId, setSelectedWarehouseId] = useState(
    user.role === 'warehouse_manager' && user.warehouse_id ? String(user.warehouse_id) : ''
  )

  const [transfers, setTransfers] = useState([])
  const [inventoryMap, setInventoryMap] = useState({})

  const [receivedAmounts, setReceivedAmounts] = useState({})
  const [loading, setLoading] = useState(true)
  const [actionLoadingId, setActionLoadingId] = useState(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    const loadInitialData = async () => {
      setLoading(true)
      setError('')

      try {
        const [warehousesResponse, inventoryResponse] = await Promise.all([
          apiClient.get('/warehouses/'),
          apiClient.get('/reports/warehouse-inventory-status'),
        ])

        const warehouseData = warehousesResponse.data || []
        const inventoryData = inventoryResponse.data || []

        setWarehouses(warehouseData)

        const map = {}
        inventoryData.forEach((item) => {
          map[`${item.product_id}-${item.batch_id}`] = {
            product: item.product,
            batch_number: item.batch_number,
          }
        })

        setInventoryMap(map)

        if (user.role === 'warehouse_manager' && user.warehouse_id) {
          setSelectedWarehouseId(String(user.warehouse_id))
        } else if (!selectedWarehouseId && warehouseData.length > 0) {
          setSelectedWarehouseId(String(warehouseData[0].id))
        }
      } catch (err) {
        const detail = err?.response?.data?.detail
        setError(detail || 'خطا در دریافت اطلاعات کارتابل')
      } finally {
        setLoading(false)
      }
    }

    loadInitialData()
  }, [user])

  useEffect(() => {
    if (!selectedWarehouseId) return

    const loadTransfers = async () => {
      setLoading(true)
      setError('')
      setSuccess('')

      try {
        const response = await apiClient.get(`/transfers/my-warehouse/${selectedWarehouseId}`)
        setTransfers(response.data?.transfers || [])
      } catch (err) {
        const detail = err?.response?.data?.detail
        setError(detail || 'خطا در دریافت حواله‌ها')
      } finally {
        setLoading(false)
      }
    }

    loadTransfers()
  }, [selectedWarehouseId])

  const refreshTransfers = async () => {
    if (!selectedWarehouseId) return

    const response = await apiClient.get(`/transfers/my-warehouse/${selectedWarehouseId}`)
    setTransfers(response.data?.transfers || [])
  }

  const handleSourceApprove = async (transferId) => {
    setActionLoadingId(transferId)
    setError('')
    setSuccess('')

    try {
      const response = await apiClient.post(`/transfers/${transferId}/source-approve`)
      setSuccess(response.data?.message || 'تایید مبدأ با موفقیت انجام شد.')
      await refreshTransfers()
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(detail || 'خطا در تایید مبدأ')
    } finally {
      setActionLoadingId(null)
    }
  }

  const handleDestinationConfirm = async (transfer) => {
    const value = receivedAmounts[transfer.transfer_id]
    const receivedAmount = Number(value)

    setError('')
    setSuccess('')

    if (value === undefined || value === '') {
      setError('مقدار دریافتی را وارد کنید.')
      return
    }

    if (receivedAmount < 0) {
      setError('مقدار دریافتی نمی‌تواند منفی باشد.')
      return
    }

    if (receivedAmount > Number(transfer.quantity || 0)) {
      setError('مقدار دریافتی نمی‌تواند بیشتر از مقدار ارسال‌شده باشد.')
      return
    }

    setActionLoadingId(transfer.transfer_id)

    try {
      const response = await apiClient.post(`/transfers/${transfer.transfer_id}/confirm`, {
        received_amount: receivedAmount,
      })

      setSuccess(response.data?.message || 'تایید مقصد با موفقیت انجام شد.')
      setReceivedAmounts((prev) => ({
        ...prev,
        [transfer.transfer_id]: '',
      }))

      await refreshTransfers()
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(detail || 'خطا در تایید مقصد')
    } finally {
      setActionLoadingId(null)
    }
  }

  const pendingTransfers = transfers.filter((transfer) => (
    transfer.status === 'pending_source_approval' ||
    transfer.status === 'pending_destination' ||
    transfer.status === 'disputed'
  ))

  const completedTransfers = transfers.filter((transfer) => (
    transfer.status !== 'pending_source_approval' &&
    transfer.status !== 'pending_destination' &&
    transfer.status !== 'disputed'
  ))

  const renderTransferCard = (transfer) => {
    const productInfo = inventoryMap[`${transfer.product_id}-${transfer.batch_id}`]
    const isSender = transfer.role_in_transfer === 'sender'
    const isReceiver = transfer.role_in_transfer === 'receiver'

    const canSourceApprove = isSender && transfer.status === 'pending_source_approval'
    const canDestinationConfirm = isReceiver && transfer.status === 'pending_destination'

    return (
      <article className="transfer-card" key={transfer.transfer_id}>
        <div className="transfer-card-header">
          <div>
            <h3>حواله #{transfer.transfer_id}</h3>
            <p>{statusLabel(transfer.status)}</p>
          </div>

          <span className={`status-pill status-${transfer.status}`}>
            {roleLabel(transfer.role_in_transfer)}
          </span>
        </div>

        <div className="transfer-detail-grid">
          <div>
            <span>مبدأ</span>
            <strong>انبار {transfer.source_warehouse_id}</strong>
          </div>

          <div>
            <span>مقصد</span>
            <strong>انبار {transfer.destination_warehouse_id}</strong>
          </div>

          <div>
            <span>کالا</span>
            <strong>{productInfo?.product || `کالا ${transfer.product_id}`}</strong>
          </div>

          <div>
            <span>بچ</span>
            <strong>{productInfo?.batch_number || transfer.batch_id}</strong>
          </div>

          <div>
            <span>مقدار</span>
            <strong>{formatNumber(transfer.quantity)}</strong>
          </div>

          <div>
            <span>تاریخ</span>
            <strong>{formatTehranDate(transfer.created_at)}</strong>
          </div>
        </div>

        {/* TRANSFER_PACKAGING_CARD_START */}
        {Array.isArray(transfer.packaging_items) &&
          transfer.packaging_items.length > 0 && (
            <section className="selected-stock-card">
              <h3>اقلام بسته‌بندی حواله</h3>

              <div className="inventory-list">
                {transfer.packaging_items.map((item) => (
                  <article
                    className="inventory-item"
                    key={item.id || `${transfer.transfer_id}-${item.material_id}`}
                  >
                    <div className="inventory-item-header">
                      <h3>{item.material_name}</h3>
                      <span>{item.material_sku}</span>
                    </div>

                    <div className="transfer-detail-grid">
                      <div>
                        <span>مرحله مصرف</span>
                        <strong>
                          {packagingStageLabel(
                            item.consumption_stage
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>مقدار لازم</span>
                        <strong>
                          {formatNumber(item.required_quantity)}
                        </strong>
                      </div>

                      <div>
                        <span>رزروشده</span>
                        <strong>
                          {formatNumber(item.reserved_quantity)}
                        </strong>
                      </div>

                      <div>
                        <span>صادرشده</span>
                        <strong>
                          {formatNumber(item.issued_quantity)}
                        </strong>
                      </div>

                      <div>
                        <span>دریافت‌شده</span>
                        <strong>
                          {formatNumber(item.received_quantity)}
                        </strong>
                      </div>

                      <div>
                        <span>کسری</span>
                        <strong>
                          {formatNumber(item.missing_quantity)}
                        </strong>
                      </div>

                      <div>
                        <span>آسیب‌دیده</span>
                        <strong>
                          {formatNumber(item.damaged_quantity)}
                        </strong>
                      </div>

                      <div>
                        <span>وضعیت</span>
                        <strong>
                          {packagingStatusLabel(item.status)}
                        </strong>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}
        {/* TRANSFER_PACKAGING_CARD_END */}

        {canSourceApprove && (
          <button
            className="action-button"
            onClick={() => handleSourceApprove(transfer.transfer_id)}
            disabled={actionLoadingId === transfer.transfer_id}
          >
            {actionLoadingId === transfer.transfer_id ? 'در حال تایید...' : 'تایید خروج از مبدأ'}
          </button>
        )}

        {canDestinationConfirm && (
          <div className="confirm-box">
            <label>
              مقدار دریافتی
              <input
                type="number"
                min="0"
                step="0.01"
                value={receivedAmounts[transfer.transfer_id] ?? transfer.quantity}
                onChange={(event) => {
                  setReceivedAmounts((prev) => ({
                    ...prev,
                    [transfer.transfer_id]: event.target.value,
                  }))
                }}
              />
            </label>

            <button
              className="action-button"
              onClick={() => handleDestinationConfirm(transfer)}
              disabled={actionLoadingId === transfer.transfer_id}
            >
              {actionLoadingId === transfer.transfer_id ? 'در حال ثبت...' : 'ثبت دریافت مقصد'}
            </button>
          </div>
        )}
      </article>
    )
  }

  return (
    <>
      <PageHeader title="کارتابل تاییدها" onBack={onBack} />

      {user.role === 'admin' && (
        <section className="inventory-toolbar">
          <select
            value={selectedWarehouseId}
            onChange={(event) => setSelectedWarehouseId(event.target.value)}
          >
            <option value="">انتخاب انبار</option>
            {warehouses.map((warehouse) => (
              <option key={warehouse.id} value={warehouse.id}>
                {warehouse.name}
              </option>
            ))}
          </select>
        </section>
      )}

      {error && (
        <section className="error-box transfer-message">
          {error}
        </section>
      )}

      {success && (
        <section className="success-box transfer-message">
          {success}
        </section>
      )}

      {loading && (
        <section className="welcome-card">
          <p>در حال دریافت حواله‌ها...</p>
        </section>
      )}

      {!loading && (
        <>
          <section className="summary-row">
            <div className="summary-card">
              <span>حواله‌های نیازمند اقدام</span>
              <strong>{formatNumber(pendingTransfers.length)}</strong>
            </div>

            <div className="summary-card">
              <span>کل حواله‌های قابل مشاهده</span>
              <strong>{formatNumber(transfers.length)}</strong>
            </div>
          </section>

          <section className="section-title">
            <h3>نیازمند اقدام</h3>
          </section>

          <section className="transfer-list">
            {pendingTransfers.length === 0 ? (
              <div className="empty-state">
                حواله‌ای برای اقدام وجود ندارد.
              </div>
            ) : (
              pendingTransfers.map(renderTransferCard)
            )}
          </section>

          <section className="section-title">
            <h3>سوابق اخیر</h3>
          </section>

          <section className="transfer-list">
            {completedTransfers.length === 0 ? (
              <div className="empty-state">
                سابقه‌ای برای نمایش وجود ندارد.
              </div>
            ) : (
              completedTransfers.slice(0, 6).map(renderTransferCard)
            )}
          </section>
        </>
      )}
    </>
  )
}

function PackagingManagementPage({ user, onBack }) {
  const createEmptyItem = (isPrimary = false) => ({
    material_id: '',
    quantity_per_product: '1',
    consumption_stage: 'production',
    rounding_mode: 'exact',
    is_primary: isPrimary,
  })

  const [dashboard, setDashboard] = useState({
    warehouses: [],
    products: [],
    materials: [],
    inventories: [],
    profiles: [],
  })

  const [materialForm, setMaterialForm] = useState({
    name: '',
    sku: '',
    material_type: 'container',
    capacity_grams: '',
    description: '',
  })

  const [inventoryForm, setInventoryForm] = useState({
    warehouse_id: '',
    material_id: '',
    quantity: '',
    action_type: 'manual_increase',
    reason: '',
  })

  const [profileForm, setProfileForm] = useState({
    product_id: '',
    name: '',
    items: [createEmptyItem(true)],
  })

  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const readApiError = (err, fallback) => {
    const detail = err?.response?.data?.detail

    return typeof detail === 'string'
      ? detail
      : detail?.message || fallback
  }

  const loadDashboard = async () => {
    const response = await apiClient.get(
      '/admin-panel/packaging-dashboard'
    )

    const data = response.data || {}

    setDashboard({
      warehouses: data.warehouses || [],
      products: data.products || [],
      materials: data.materials || [],
      inventories: data.inventories || [],
      profiles: data.profiles || [],
    })
  }

  useEffect(() => {
    const loadInitialData = async () => {
      setLoading(true)
      setError('')

      try {
        if (user?.role === 'admin') {
          await loadDashboard()
        }
      } catch (err) {
        setError(
          readApiError(
            err,
            'خطا در دریافت اطلاعات بسته‌بندی'
          )
        )
      } finally {
        setLoading(false)
      }
    }

    loadInitialData()
  }, [user])

  const handleCreateMaterial = async (event) => {
    event.preventDefault()
    setError('')
    setSuccess('')

    const name = materialForm.name.trim()
    const sku = materialForm.sku.trim()
    const capacityText =
      String(materialForm.capacity_grams || '').trim()

    if (!name || !sku) {
      setError('نام و کد بسته‌بندی الزامی است.')
      return
    }

    let capacity = null

    if (capacityText) {
      capacity = Number(capacityText)

      if (!Number.isFinite(capacity) || capacity <= 0) {
        setError('ظرفیت باید عددی مثبت باشد.')
        return
      }
    }

    setSubmitting('material')

    try {
      await apiClient.post(
        '/admin-panel/packaging-materials',
        {
          name,
          sku,
          material_type: materialForm.material_type,
          capacity_grams: capacity,
          description:
            materialForm.description.trim() || null,
        }
      )

      setMaterialForm({
        name: '',
        sku: '',
        material_type: 'container',
        capacity_grams: '',
        description: '',
      })

      await loadDashboard()
      setSuccess('قلم بسته‌بندی ثبت شد.')
    } catch (err) {
      setError(
        readApiError(
          err,
          'خطا در ثبت قلم بسته‌بندی'
        )
      )
    } finally {
      setSubmitting('')
    }
  }

  const handleAdjustInventory = async (event) => {
    event.preventDefault()
    setError('')
    setSuccess('')

    const quantity = Number(inventoryForm.quantity)

    if (
      !inventoryForm.warehouse_id ||
      !inventoryForm.material_id
    ) {
      setError('انبار و قلم بسته‌بندی را انتخاب کنید.')
      return
    }

    if (!Number.isInteger(quantity) || quantity <= 0) {
      setError('مقدار باید یک عدد صحیح مثبت باشد.')
      return
    }

    setSubmitting('inventory')

    try {
      await apiClient.post(
        '/admin-panel/packaging-inventory/adjust',
        {
          warehouse_id: Number(
            inventoryForm.warehouse_id
          ),
          material_id: Number(
            inventoryForm.material_id
          ),
          quantity,
          action_type: inventoryForm.action_type,
          reason: inventoryForm.reason.trim() || null,
        }
      )

      setInventoryForm((previous) => ({
        ...previous,
        quantity: '',
        reason: '',
      }))

      await loadDashboard()
      setSuccess('موجودی بسته‌بندی ثبت شد.')
    } catch (err) {
      setError(
        readApiError(
          err,
          'خطا در ثبت موجودی بسته‌بندی'
        )
      )
    } finally {
      setSubmitting('')
    }
  }

  const updateProfileItem = (index, field, value) => {
    setProfileForm((previous) => ({
      ...previous,
      items: previous.items.map((item, itemIndex) =>
        itemIndex === index
          ? { ...item, [field]: value }
          : item
      ),
    }))
  }

  const selectPrimaryItem = (index) => {
    setProfileForm((previous) => ({
      ...previous,
      items: previous.items.map((item, itemIndex) => ({
        ...item,
        is_primary: itemIndex === index,
      })),
    }))
  }

  const addProfileItem = () => {
    setProfileForm((previous) => ({
      ...previous,
      items: [
        ...previous.items,
        createEmptyItem(false),
      ],
    }))
  }

  const removeProfileItem = (index) => {
    setProfileForm((previous) => {
      if (previous.items.length <= 1) {
        return previous
      }

      const removedPrimary =
        previous.items[index].is_primary

      const items = previous.items.filter(
        (_, itemIndex) => itemIndex !== index
      )

      if (removedPrimary && items.length > 0) {
        items[0] = {
          ...items[0],
          is_primary: true,
        }
      }

      return {
        ...previous,
        items,
      }
    })
  }

  const handleCreateProfile = async (event) => {
    event.preventDefault()
    setError('')
    setSuccess('')

    const productId = Number(profileForm.product_id)
    const profileName = profileForm.name.trim()

    if (!productId || !profileName) {
      setError('محصول و نام پروفایل الزامی است.')
      return
    }

    const materialIds = profileForm.items.map(
      (item) => Number(item.material_id)
    )

    if (materialIds.some((value) => !value)) {
      setError('برای همه ردیف‌ها قلم بسته‌بندی را انتخاب کنید.')
      return
    }

    if (
      new Set(materialIds).size !== materialIds.length
    ) {
      setError(
        'هر قلم بسته‌بندی فقط یک‌بار قابل انتخاب است.'
      )
      return
    }

    const primaryItems = profileForm.items.filter(
      (item) => item.is_primary
    )

    if (primaryItems.length !== 1) {
      setError(
        'دقیقاً یک قلم باید به‌عنوان ظرف اصلی انتخاب شود.'
      )
      return
    }

    const items = []

    for (const item of profileForm.items) {
      const ratio = Number(item.quantity_per_product)

      if (!Number.isFinite(ratio) || ratio <= 0) {
        setError('نسبت مصرف باید عددی مثبت باشد.')
        return
      }

      if (
        item.rounding_mode === 'exact' &&
        !Number.isInteger(ratio)
      ) {
        setError(
          'در حالت دقیق، نسبت مصرف باید عدد صحیح باشد.'
        )
        return
      }

      items.push({
        material_id: Number(item.material_id),
        quantity_per_product: ratio,
        consumption_stage:
          item.consumption_stage,
        rounding_mode: item.rounding_mode,
        is_primary: item.is_primary,
      })
    }

    setSubmitting('profile')

    try {
      const response = await apiClient.post(
        '/admin-panel/packaging-profiles',
        {
          product_id: productId,
          name: profileName,
          items,
        }
      )

      setProfileForm({
        product_id: '',
        name: '',
        items: [createEmptyItem(true)],
      })

      await loadDashboard()

      setSuccess(
        `پروفایل نسخه ${
          response.data?.version || ''
        } ساخته و فعال شد.`
      )
    } catch (err) {
      setError(
        readApiError(
          err,
          'خطا در ایجاد پروفایل بسته‌بندی'
        )
      )
    } finally {
      setSubmitting('')
    }
  }

  const materialTypeLabel = (value) => {
    const labels = {
      container: 'ظرف اصلی',
      lid: 'درپوش',
      label: 'برچسب',
      inner_box: 'جعبه داخلی',
      carton: 'کارتن',
      pallet: 'پالت',
      other: 'سایر',
    }

    return labels[value] || value || '-'
  }

  if (user?.role !== 'admin') {
    return (
      <>
        <PageHeader
          title="بسته‌بندی و موجودی"
          onBack={onBack}
        />

        <section className="error-box transfer-message">
          دسترسی به مدیریت بسته‌بندی فقط برای مدیر سامانه مجاز است.
        </section>
      </>
    )
  }

  return (
    <>
      {/* PACKAGING_MANAGEMENT_PAGE_START */}
      <PageHeader
        title="بسته‌بندی و موجودی"
        onBack={onBack}
      />

      {loading && (
        <section className="welcome-card">
          <p>در حال دریافت اطلاعات بسته‌بندی...</p>
        </section>
      )}

      {error && (
        <section className="error-box transfer-message">
          {error}
        </section>
      )}

      {success && (
        <section className="success-box transfer-message">
          {success}
        </section>
      )}

      {!loading && (
        <>
          <section className="summary-row">
            <div className="summary-card">
              <span>اقلام بسته‌بندی</span>
              <strong>
                {formatNumber(dashboard.materials.length)}
              </strong>
            </div>

            <div className="summary-card">
              <span>پروفایل‌های فعال</span>
              <strong>
                {formatNumber(dashboard.profiles.length)}
              </strong>
            </div>

            <div className="summary-card">
              <span>موجودی‌های ثبت‌شده</span>
              <strong>
                {formatNumber(dashboard.inventories.length)}
              </strong>
            </div>
          </section>

          <section className="welcome-card">
            <div className="section-title">
              <h3>ثبت قلم بسته‌بندی</h3>
            </div>

            <form
              className="transfer-form"
              onSubmit={handleCreateMaterial}
            >
              <label>
                نام بسته‌بندی
                <input
                  type="text"
                  value={materialForm.name}
                  onChange={(event) =>
                    setMaterialForm((previous) => ({
                      ...previous,
                      name: event.target.value,
                    }))
                  }
                  required
                />
              </label>

              <label>
                کد بسته‌بندی
                <input
                  type="text"
                  value={materialForm.sku}
                  onChange={(event) =>
                    setMaterialForm((previous) => ({
                      ...previous,
                      sku: event.target.value,
                    }))
                  }
                  required
                />
              </label>

              <label>
                نوع
                <select
                  value={materialForm.material_type}
                  onChange={(event) =>
                    setMaterialForm((previous) => ({
                      ...previous,
                      material_type: event.target.value,
                    }))
                  }
                >
                  <option value="container">ظرف اصلی</option>
                  <option value="lid">درپوش</option>
                  <option value="label">برچسب</option>
                  <option value="inner_box">جعبه داخلی</option>
                  <option value="carton">کارتن</option>
                  <option value="pallet">پالت</option>
                  <option value="other">سایر</option>
                </select>
              </label>

              <label>
                ظرفیت به گرم
                <input
                  type="number"
                  min="0.000001"
                  step="any"
                  value={materialForm.capacity_grams}
                  onChange={(event) =>
                    setMaterialForm((previous) => ({
                      ...previous,
                      capacity_grams: event.target.value,
                    }))
                  }
                />
              </label>

              <label>
                توضیحات
                <textarea
                  rows="3"
                  value={materialForm.description}
                  onChange={(event) =>
                    setMaterialForm((previous) => ({
                      ...previous,
                      description: event.target.value,
                    }))
                  }
                />
              </label>

              <button
                type="submit"
                disabled={submitting === 'material'}
              >
                {submitting === 'material'
                  ? 'در حال ثبت...'
                  : 'ثبت بسته‌بندی'}
              </button>
            </form>
          </section>

          <section className="welcome-card">
            <div className="section-title">
              <h3>تنظیم موجودی بسته‌بندی</h3>
            </div>

            <form
              className="transfer-form"
              onSubmit={handleAdjustInventory}
            >
              <label>
                انبار
                <select
                  value={inventoryForm.warehouse_id}
                  onChange={(event) =>
                    setInventoryForm((previous) => ({
                      ...previous,
                      warehouse_id: event.target.value,
                    }))
                  }
                  required
                >
                  <option value="">انتخاب انبار</option>

                  {dashboard.warehouses.map((warehouse) => (
                    <option
                      key={warehouse.id}
                      value={warehouse.id}
                    >
                      {warehouse.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                قلم بسته‌بندی
                <select
                  value={inventoryForm.material_id}
                  onChange={(event) =>
                    setInventoryForm((previous) => ({
                      ...previous,
                      material_id: event.target.value,
                    }))
                  }
                  required
                >
                  <option value="">انتخاب بسته‌بندی</option>

                  {dashboard.materials.map((material) => (
                    <option
                      key={material.id}
                      value={material.id}
                    >
                      {material.name} | {material.sku}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                نوع عملیات
                <select
                  value={inventoryForm.action_type}
                  onChange={(event) =>
                    setInventoryForm((previous) => ({
                      ...previous,
                      action_type: event.target.value,
                    }))
                  }
                >
                  <option value="manual_increase">
                    افزایش موجودی
                  </option>
                  <option value="manual_decrease">
                    کاهش موجودی
                  </option>
                  <option value="damaged">آسیب‌دیده</option>
                  <option value="lost">مفقودی</option>
                </select>
              </label>

              <label>
                مقدار
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={inventoryForm.quantity}
                  onChange={(event) =>
                    setInventoryForm((previous) => ({
                      ...previous,
                      quantity: event.target.value,
                    }))
                  }
                  required
                />
              </label>

              <label>
                دلیل
                <textarea
                  rows="3"
                  value={inventoryForm.reason}
                  onChange={(event) =>
                    setInventoryForm((previous) => ({
                      ...previous,
                      reason: event.target.value,
                    }))
                  }
                />
              </label>

              <button
                type="submit"
                disabled={submitting === 'inventory'}
              >
                {submitting === 'inventory'
                  ? 'در حال ثبت...'
                  : 'ثبت تغییر موجودی'}
              </button>
            </form>
          </section>

          <section className="welcome-card">
            <div className="section-title">
              <h3>ایجاد نسخه جدید پروفایل</h3>
            </div>

            <form
              className="transfer-form"
              onSubmit={handleCreateProfile}
            >
              <label>
                کالا
                <select
                  value={profileForm.product_id}
                  onChange={(event) =>
                    setProfileForm((previous) => ({
                      ...previous,
                      product_id: event.target.value,
                    }))
                  }
                  required
                >
                  <option value="">انتخاب محصول</option>

                  {dashboard.products.map((product) => (
                    <option
                      key={product.id}
                      value={product.id}
                    >
                      {product.name} | {product.sku} |{' '}
                      {formatNumber(
                        product.unit_weight_grams
                      )}{' '}
                      گرم
                    </option>
                  ))}
                </select>
              </label>

              <label>
                نام پروفایل
                <input
                  type="text"
                  value={profileForm.name}
                  onChange={(event) =>
                    setProfileForm((previous) => ({
                      ...previous,
                      name: event.target.value,
                    }))
                  }
                  required
                />
              </label>

              {profileForm.items.map((item, index) => (
                <article
                  className="selected-stock-card"
                  key={`packaging-item-${index}`}
                >
                  <div className="inventory-item-header">
                    <h3>
                      قلم {formatNumber(index + 1)}
                    </h3>

                    {profileForm.items.length > 1 && (
                      <button
                        type="button"
                        className="danger-button"
                        onClick={() =>
                          removeProfileItem(index)
                        }
                      >
                        حذف
                      </button>
                    )}
                  </div>

                  <label>
                    قلم بسته‌بندی
                    <select
                      value={item.material_id}
                      onChange={(event) =>
                        updateProfileItem(
                          index,
                          'material_id',
                          event.target.value
                        )
                      }
                      required
                    >
                      <option value="">انتخاب بسته‌بندی</option>

                      {dashboard.materials.map((material) => (
                        <option
                          key={material.id}
                          value={material.id}
                        >
                          {material.name} | {material.sku} |{' '}
                          {materialTypeLabel(
                            material.material_type
                          )}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    مقدار مصرف برای هر محصول
                    <input
                      type="number"
                      min="0.000001"
                      step="any"
                      value={item.quantity_per_product}
                      onChange={(event) =>
                        updateProfileItem(
                          index,
                          'quantity_per_product',
                          event.target.value
                        )
                      }
                      required
                    />
                  </label>

                  <label>
                    مرحله مصرف
                    <select
                      value={item.consumption_stage}
                      onChange={(event) =>
                        updateProfileItem(
                          index,
                          'consumption_stage',
                          event.target.value
                        )
                      }
                    >
                      <option value="production">
                        هنگام تولید
                      </option>
                      <option value="dispatch">
                        هنگام ارسال
                      </option>
                    </select>
                  </label>

                  <label>
                    روش گردکردن
                    <select
                      value={item.rounding_mode}
                      onChange={(event) =>
                        updateProfileItem(
                          index,
                          'rounding_mode',
                          event.target.value
                        )
                      }
                    >
                      <option value="exact">دقیق</option>
                      <option value="ceil">
                        رو به بالا
                      </option>
                    </select>
                  </label>

                  <label>
                    <input
                      type="radio"
                      name="primary-packaging-item"
                      checked={item.is_primary}
                      onChange={() =>
                        selectPrimaryItem(index)
                      }
                    />
                    {' '}
                    ظرف اصلی
                  </label>
                </article>
              ))}

              <button
                type="button"
                className="secondary-button"
                onClick={addProfileItem}
              >
                افزودن قلم بسته‌بندی
              </button>

              <button
                type="submit"
                disabled={submitting === 'profile'}
              >
                {submitting === 'profile'
                  ? 'در حال ایجاد...'
                  : 'ایجاد و فعال‌سازی پروفایل'}
              </button>
            </form>
          </section>

          <section className="welcome-card">
            <div className="section-title">
              <h3>موجودی اقلام بسته‌بندی</h3>
            </div>

            {dashboard.inventories.length === 0 ? (
              <div className="empty-state">
                هنوز موجودی بسته‌بندی ثبت نشده است.
              </div>
            ) : (
              <div className="inventory-list">
                {dashboard.inventories.map((inventory) => (
                  <article
                    className="inventory-item"
                    key={inventory.id}
                  >
                    <div className="inventory-item-header">
                      <h3>{inventory.material_name}</h3>
                      <span>{inventory.material_sku}</span>
                    </div>

                    <p>{inventory.warehouse_name}</p>

                    <div className="quantity-grid">
                      <div>
                        <span>موجودی کل</span>
                        <strong>
                          {formatNumber(inventory.quantity)}
                        </strong>
                      </div>

                      <div>
                        <span>رزروشده</span>
                        <strong>
                          {formatNumber(
                            inventory.reserved_quantity
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>آزاد</span>
                        <strong>
                          {formatNumber(
                            inventory.free_quantity
                          )}
                        </strong>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}
      {/* PACKAGING_MANAGEMENT_PAGE_END */}
    </>
  )
}


function ProductionPage({ user, onBack }) {
  const [warehouses, setWarehouses] = useState([])
  const [products, setProducts] = useState([])

  const [warehouseId, setWarehouseId] = useState(
    user.role === 'warehouse_manager' && user.warehouse_id
      ? String(user.warehouse_id)
      : ''
  )
  const [productId, setProductId] = useState('')
  const [produceQuantity, setProduceQuantity] = useState('')
  const [batchNumber, setBatchNumber] = useState('')
  const [expiryDays, setExpiryDays] = useState('730')

  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(null)

  const loadOptions = async () => {
    const response = await apiClient.get(
      '/production/options'
    )

    const data = response.data || {}

    setWarehouses(data.warehouses || [])
    setProducts(data.products || [])

    if (
      user.role === 'warehouse_manager' &&
      user.warehouse_id
    ) {
      setWarehouseId(String(user.warehouse_id))
    }
  }

  useEffect(() => {
    const loadInitialData = async () => {
      setLoading(true)
      setError('')

      try {
        await loadOptions()
      } catch (err) {
        const detail = err?.response?.data?.detail

        setError(
          typeof detail === 'string'
            ? detail
            : detail?.message ||
              'خطا در دریافت اطلاعات تولید'
        )
      } finally {
        setLoading(false)
      }
    }

    loadInitialData()
  }, [user])

  const selectedProduct = products.find(
    (item) =>
      String(item.product_id) === String(productId)
  )

  const handleSubmit = async (event) => {
    event.preventDefault()

    setError('')
    setSuccess(null)

    if (!warehouseId) {
      setError('انبار تولید را انتخاب کنید.')
      return
    }

    if (!selectedProduct) {
      setError('محصول نهایی را انتخاب کنید.')
      return
    }

    if (!selectedProduct.configuration_ready) {
      setError(
        'پیکربندی این محصول برای تولید کامل نیست.'
      )
      return
    }

    const quantity = Number(produceQuantity)

    if (
      !Number.isFinite(quantity) ||
      quantity <= 0 ||
      !Number.isInteger(quantity)
    ) {
      setError(
        'تعداد تولید باید یک عدد صحیح مثبت باشد.'
      )
      return
    }

    const normalizedBatch = batchNumber.trim()

    if (!normalizedBatch) {
      setError('شماره بچ تولید الزامی است.')
      return
    }

    const normalizedExpiryDays = Number(expiryDays)

    if (
      !Number.isFinite(normalizedExpiryDays) ||
      normalizedExpiryDays <= 0 ||
      !Number.isInteger(normalizedExpiryDays)
    ) {
      setError(
        'مدت اعتبار باید یک عدد صحیح مثبت باشد.'
      )
      return
    }

    setSubmitting(true)

    try {
      const response = await apiClient.post(
        '/production/manufacture',
        {
          warehouse_id: Number(warehouseId),
          final_product_id: selectedProduct.product_id,
          produce_quantity: quantity,
          new_batch_number: normalizedBatch,
          expiry_days: normalizedExpiryDays,
        }
      )

      setSuccess(response.data)
      setProduceQuantity('')
      setBatchNumber('')
    } catch (err) {
      const detail = err?.response?.data?.detail

      setError(
        typeof detail === 'string'
          ? detail
          : detail?.message || 'خطا در ثبت عملیات تولید'
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      {/* PRODUCTION_PAGE_OPERATIONAL_START */}
      <PageHeader
        title="تولید و فرمولاسیون"
        onBack={onBack}
      />

      {loading && (
        <section className="welcome-card">
          <p>در حال دریافت اطلاعات تولید...</p>
        </section>
      )}

      {error && (
        <section className="error-box transfer-message">
          {error}
        </section>
      )}

      {success && (
        <section className="success-box transfer-message">
          <strong>تولید با موفقیت ثبت شد.</strong>

          <span>
            شناسه عملیات تولید:
            {' '}
            {success.production_run_id || '-'}
          </span>

          <span>
            شناسه بچ:
            {' '}
            {success.batch_id || '-'}
          </span>

          <span>
            تعداد تولیدشده:
            {' '}
            {formatNumber(success.produced_quantity)}
          </span>

          <span>
            نسخه پروفایل بسته‌بندی:
            {' '}
            {formatNumber(
              success.packaging_profile_version
            )}
          </span>
        </section>
      )}

      {!loading && (
        <form
          className="transfer-form"
          onSubmit={handleSubmit}
        >
          <label>
            انبار تولید
            <select
              value={warehouseId}
              onChange={(event) =>
                setWarehouseId(event.target.value)
              }
              disabled={
                user.role === 'warehouse_manager'
              }
              required
            >
              <option value="">
                انتخاب انبار تولید
              </option>

              {warehouses.map((warehouse) => (
                <option
                  key={warehouse.id}
                  value={warehouse.id}
                >
                  {warehouse.name}
                  {warehouse.location
                    ? ` - ${warehouse.location}`
                    : ''}
                </option>
              ))}
            </select>
          </label>

          <label>
            محصول نهایی
            <select
              value={productId}
              onChange={(event) => {
                setProductId(event.target.value)
                setSuccess(null)
              }}
              required
            >
              <option value="">
                انتخاب محصول نهایی
              </option>

              {products.map((product) => (
                <option
                  key={product.product_id}
                  value={product.product_id}
                >
                  {product.product_name}
                  {' | '}
                  {product.product_sku}
                  {product.configuration_ready
                    ? ''
                    : ' | پیکربندی ناقص'}
                </option>
              ))}
            </select>
          </label>

          {selectedProduct && (
            <section className="selected-stock-card">
              <h3>{selectedProduct.product_name}</h3>

              <p>
                کد محصول:
                {' '}
                {selectedProduct.product_sku}
              </p>

              <p>
                وزن هر واحد:
                {' '}
                {formatNumber(
                  selectedProduct.unit_weight_grams
                )}
                {' '}
                گرم
              </p>

              <p>
                مجموع فرمول:
                {' '}
                {formatNumber(
                  selectedProduct.recipe_total_percentage
                )}
                ?
              </p>

              {selectedProduct.configuration_ready ? (
                <div className="success-box transfer-message">
                  پیکربندی محصول برای تولید کامل است.
                </div>
              ) : (
                <div className="error-box transfer-message">
                  <strong>
                    این محصول برای تولید آماده نیست.
                  </strong>

                  {(selectedProduct.configuration_errors || [])
                    .map((message) => (
                      <span key={message}>
                        {message}
                      </span>
                    ))}
                </div>
              )}

              {selectedProduct.recipe_components?.length > 0 && (
                <>
                  <div className="section-title">
                    <h3>فرمول مواد اولیه</h3>
                  </div>

                  <div className="inventory-list">
                    {selectedProduct.recipe_components.map(
                      (ingredient) => (
                        <article
                          className="inventory-item"
                          key={ingredient.ingredient_id}
                        >
                          <div className="inventory-item-header">
                            <h3>
                              {ingredient.ingredient_name}
                            </h3>

                            <span>
                              {ingredient.ingredient_sku}
                            </span>
                          </div>

                          <div className="quantity-grid">
                            <div>
                              <span>درصد</span>
                              <strong>
                                {formatNumber(
                                  ingredient.percentage
                                )}
                                ?
                              </strong>
                            </div>

                            <div>
                              <span>واحد پایه</span>
                              <strong>
                                {ingredient.base_unit}
                              </strong>
                            </div>
                          </div>
                        </article>
                      )
                    )}
                  </div>
                </>
              )}

              {selectedProduct.packaging_profile && (
                <>
                  <div className="section-title">
                    <h3>پروفایل بسته‌بندی</h3>
                  </div>

                  <p>
                    {selectedProduct.packaging_profile
                      .profile_name}
                    {' | '}
                    نسخه
                    {' '}
                    {formatNumber(
                      selectedProduct.packaging_profile
                        .profile_version
                    )}
                  </p>

                  <div className="inventory-list">
                    {selectedProduct.packaging_profile.items.map(
                      (item) => (
                        <article
                          className="inventory-item"
                          key={item.profile_item_id}
                        >
                          <div className="inventory-item-header">
                            <h3>{item.material_name}</h3>
                            <span>{item.material_sku}</span>
                          </div>

                          <div className="transfer-detail-grid">
                            <div>
                              <span>نوع</span>
                              <strong>
                                {item.material_type}
                              </strong>
                            </div>

                            <div>
                              <span>مرحله مصرف</span>
                              <strong>
                                {packagingStageLabel(
                                  item.consumption_stage
                                )}
                              </strong>
                            </div>

                            <div>
                              <span>مقدار هر محصول</span>
                              <strong>
                                {formatNumber(
                                  item.quantity_per_product
                                )}
                              </strong>
                            </div>

                            <div>
                              <span>ظرف اصلی</span>
                              <strong>
                                {item.is_primary
                                  ? 'بله'
                                  : 'خیر'}
                              </strong>
                            </div>
                          </div>
                        </article>
                      )
                    )}
                  </div>
                </>
              )}
            </section>
          )}

          <label>
            تعداد تولید
            <input
              type="number"
              min="1"
              step="1"
              value={produceQuantity}
              onChange={(event) =>
                setProduceQuantity(event.target.value)
              }
              placeholder="مثلاً 100"
              required
            />
          </label>

          <label>
            شماره بچ تولید
            <input
              type="text"
              value={batchNumber}
              onChange={(event) =>
                setBatchNumber(event.target.value)
              }
              placeholder="مثلاً PRD-1405-001"
              required
            />
          </label>

          <label>
            مدت اعتبار به روز
            <input
              type="number"
              min="1"
              step="1"
              value={expiryDays}
              onChange={(event) =>
                setExpiryDays(event.target.value)
              }
              required
            />
          </label>

          <button
            type="submit"
            disabled={
              submitting ||
              !selectedProduct?.configuration_ready
            }
          >
            {submitting
              ? 'در حال ثبت عملیات تولید...'
              : 'ثبت تولید و ایجاد موجودی'}
          </button>
        </form>
      )}
      {/* PRODUCTION_PAGE_OPERATIONAL_END */}
    </>
  )
}


function DisputesPage({ user, onBack }) {
  const [disputes, setDisputes] = useState([])
  const [loading, setLoading] = useState(true)
  const [resolvingId, setResolvingId] = useState(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [search, setSearch] = useState('')
  const [resolutionForms, setResolutionForms] = useState({})

  const loadDisputes = async () => {
    const response = await apiClient.get('/reports/disputes/active')
    setDisputes(response.data || [])
  }

  useEffect(() => {
    const loadInitialData = async () => {
      setLoading(true)
      setError('')

      try {
        await loadDisputes()
      } catch (err) {
        const detail = err?.response?.data?.detail

        setError(
          typeof detail === 'string'
            ? detail
            : detail?.message || 'خطا در دریافت مغایرت‌ها'
        )
      } finally {
        setLoading(false)
      }
    }

    loadInitialData()
  }, [])

  const updateResolutionForm = (disputeId, field, value) => {
    setResolutionForms((previous) => ({
      ...previous,
      [disputeId]: {
        action_taken:
          previous[disputeId]?.action_taken || '',
        resolution_notes:
          previous[disputeId]?.resolution_notes || '',
        [field]: value,
      },
    }))
  }

  const handleResolveDispute = async (item) => {
    const form = resolutionForms[item.dispute_id] || {}
    const actionTaken = form.action_taken || ''
    const resolutionNotes = (
      form.resolution_notes || ''
    ).trim()

    setError('')
    setSuccess('')

    if (!actionTaken) {
      setError('نوع اقدام برای حل مغایرت را انتخاب کنید.')
      return
    }

    if (!resolutionNotes) {
      setError('توضیحات حل مغایرت الزامی است.')
      return
    }

    setResolvingId(item.dispute_id)

    try {
      const response = await apiClient.post(
        `/transfers/disputes/${item.dispute_id}/resolve`,
        {
          action_taken: actionTaken,
          resolution_notes: resolutionNotes,
        }
      )

      setSuccess(
        response.data?.message ||
          `مغایرت شماره ${item.dispute_id} با موفقیت حل شد.`
      )

      setResolutionForms((previous) => {
        const updated = { ...previous }
        delete updated[item.dispute_id]
        return updated
      })

      await loadDisputes()
    } catch (err) {
      const detail = err?.response?.data?.detail

      setError(
        typeof detail === 'string'
          ? detail
          : detail?.message || 'خطا در حل مغایرت'
      )
    } finally {
      setResolvingId(null)
    }
  }

  const filteredDisputes = disputes.filter((item) => {
    const keyword = search.trim().toLowerCase()

    if (!keyword) return true

    return (
      String(item.product_name || '')
        .toLowerCase()
        .includes(keyword) ||
      String(item.source_warehouse || '')
        .toLowerCase()
        .includes(keyword) ||
      String(item.destination_warehouse || '')
        .toLowerCase()
        .includes(keyword) ||
      String(item.transfer_id || '').includes(keyword) ||
      String(item.dispute_id || '').includes(keyword)
    )
  })

  const totalMissing = filteredDisputes.reduce(
    (sum, item) =>
      sum + Number(item.missing_amount || 0),
    0
  )

  return (
    <>
      {/* DISPUTE_RESOLUTION_UI_START */}
      <PageHeader
        title="مغایرت‌ها و تیکت‌ها"
        onBack={onBack}
      />

      <section className="inventory-toolbar">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="جستجو با نام محصول، شماره حواله یا انبار..."
        />
      </section>

      {loading && (
        <section className="welcome-card">
          <p>در حال دریافت مغایرت‌ها...</p>
        </section>
      )}

      {error && (
        <section className="error-box transfer-message">
          {error}
        </section>
      )}

      {success && (
        <section className="success-box transfer-message">
          {success}
        </section>
      )}

      {!loading && (
        <>
          <section className="summary-row">
            <div className="summary-card">
              <span>تعداد مغایرت باز</span>
              <strong>
                {formatNumber(filteredDisputes.length)}
              </strong>
            </div>

            <div className="summary-card">
              <span>مجموع کسری</span>
              <strong>{formatNumber(totalMissing)}</strong>
            </div>
          </section>

          <section className="dispute-list">
            {filteredDisputes.length === 0 ? (
              <div className="empty-state">
                مغایرت بازی مطابق جستجو یافت نشد.
              </div>
            ) : (
              filteredDisputes.map((item) => {
                const form =
                  resolutionForms[item.dispute_id] || {}

                return (
                  <article
                    className="dispute-card"
                    key={item.dispute_id}
                  >
                    <div className="dispute-card-header">
                      <div>
                        <h3>
                          {item.product_name ||
                            `محصول ${item.product_id || '-'}`}
                        </h3>

                        <p>
                          حواله #{item.transfer_id}
                          {' | '}
                          مغایرت #{item.dispute_id}
                        </p>
                      </div>

                      <span className="dispute-status">
                        {item.status || 'OPEN'}
                      </span>
                    </div>

                    <div className="dispute-route">
                      <div>
                        <span>مبدأ</span>
                        <strong>
                          {item.source_warehouse || '-'}
                        </strong>
                      </div>

                      <div>
                        <span>مقصد</span>
                        <strong>
                          {item.destination_warehouse || '-'}
                        </strong>
                      </div>
                    </div>

                    <div className="quantity-grid">
                      <div>
                        <span>مقدار گزارش‌شده</span>
                        <strong>
                          {formatNumber(
                            item.reported_quantity
                          )}
                        </strong>
                      </div>

                      <div>
                        <span>کسری</span>
                        <strong>
                          {formatNumber(item.missing_amount)}
                        </strong>
                      </div>

                      <div>
                        <span>تاریخ</span>
                        <strong>
                          {formatTehranDate(item.created_at)}
                        </strong>
                      </div>
                    </div>

                    {user.role === 'admin' ? (
                      <div className="confirm-box">
                        <label>
                          اقدام نهایی
                          <select
                            value={form.action_taken || ''}
                            onChange={(event) =>
                              updateResolutionForm(
                                item.dispute_id,
                                'action_taken',
                                event.target.value
                              )
                            }
                          >
                            <option value="">
                              انتخاب اقدام
                            </option>

                            <option value="accept_shortage">
                              پذیرش کسری و بستن مغایرت
                            </option>

                            <option value="receive_missing">
                              دریافت کسری و تکمیل موجودی
                            </option>
                          </select>
                        </label>

                        <label>
                          توضیحات نهایی
                          <textarea
                            rows="3"
                            value={
                              form.resolution_notes || ''
                            }
                            onChange={(event) =>
                              updateResolutionForm(
                                item.dispute_id,
                                'resolution_notes',
                                event.target.value
                              )
                            }
                            placeholder="نتیجه بررسی و توضیحات نهایی را وارد کنید."
                          />
                        </label>

                        <button
                          className="action-button"
                          onClick={() =>
                            handleResolveDispute(item)
                          }
                          disabled={
                            resolvingId === item.dispute_id
                          }
                        >
                          {resolvingId === item.dispute_id
                            ? 'در حال ثبت نتیجه...'
                            : 'ثبت و بستن مغایرت'}
                        </button>
                      </div>
                    ) : (
                      <div className="ticket-note">
                        این مغایرت فقط توسط مدیر سامانه قابل
                        بررسی و حل است.
                      </div>
                    )}
                  </article>
                )
              })
            )}
          </section>
        </>
      )}
      {/* DISPUTE_RESOLUTION_UI_END */}
    </>
  )
}



// USER_MANAGEMENT_PAGE_20260731
function UserManagementPage({ onBack }) {
  const emptyCreate = {
    username: '',
    password: '',
    role: 'warehouse_manager',
    warehouse_id: '',
  }

  const [users, setUsers] = useState([])
  const [warehouses, setWarehouses] = useState([])
  const [drafts, setDrafts] = useState({})
  const [passwords, setPasswords] = useState({})
  const [createForm, setCreateForm] = useState(emptyCreate)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const readError = (err, fallback) => {
    const detail = err?.response?.data?.detail
    return typeof detail === 'string' ? detail : fallback
  }

  const loadData = async () => {
    setLoading(true)
    setError('')

    try {
      const [usersResponse, warehousesResponse] = await Promise.all([
        apiClient.get('/auth/users'),
        apiClient.get('/warehouses/'),
      ])

      const loadedUsers = usersResponse.data || []
      setUsers(loadedUsers)
      setWarehouses(warehousesResponse.data || [])

      const nextDrafts = {}
      loadedUsers.forEach((user) => {
        nextDrafts[user.id] = {
          role: user.role,
          warehouse_id: user.warehouse_id
            ? String(user.warehouse_id)
            : '',
          is_active: Boolean(user.is_active),
        }
      })
      setDrafts(nextDrafts)
    } catch (err) {
      setError(readError(err, 'خطا در دریافت اطلاعات کاربران'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const createUser = async (event) => {
    event.preventDefault()
    setError('')
    setMessage('')

    if (
      createForm.role === 'warehouse_manager' &&
      !createForm.warehouse_id
    ) {
      setError('برای انباردار باید یک انبار انتخاب شود.')
      return
    }

    setBusy('create')

    try {
      await apiClient.post('/auth/users', {
        username: createForm.username.trim(),
        password: createForm.password,
        role: createForm.role,
        warehouse_id:
          createForm.role === 'warehouse_manager'
            ? Number(createForm.warehouse_id)
            : null,
      })

      setCreateForm(emptyCreate)
      setMessage('کاربر با موفقیت ساخته شد.')
      await loadData()
    } catch (err) {
      setError(readError(err, 'خطا در ایجاد کاربر'))
    } finally {
      setBusy('')
    }
  }

  const updateDraft = (userId, field, value) => {
    setDrafts((current) => ({
      ...current,
      [userId]: {
        ...current[userId],
        [field]: value,
      },
    }))
  }

  const saveUser = async (user) => {
    const draft = drafts[user.id]

    if (
      draft.role === 'warehouse_manager' &&
      !draft.warehouse_id
    ) {
      setError('برای انباردار باید یک انبار انتخاب شود.')
      return
    }

    setBusy(`save-${user.id}`)
    setError('')
    setMessage('')

    try {
      await apiClient.put(`/auth/users/${user.id}`, {
        role: draft.role,
        warehouse_id:
          draft.role === 'warehouse_manager'
            ? Number(draft.warehouse_id)
            : null,
        is_active: Boolean(draft.is_active),
      })

      setMessage(`اطلاعات کاربر ${user.username} ذخیره شد.`)
      await loadData()
    } catch (err) {
      setError(readError(err, 'خطا در ویرایش کاربر'))
    } finally {
      setBusy('')
    }
  }

  const resetPassword = async (user) => {
    const newPassword = passwords[user.id] || ''

    if (newPassword.length < 8) {
      setError('رمز جدید باید حداقل ۸ کاراکتر باشد.')
      return
    }

    setBusy(`password-${user.id}`)
    setError('')
    setMessage('')

    try {
      await apiClient.post(
        `/auth/users/${user.id}/reset-password`,
        { new_password: newPassword }
      )

      setPasswords((current) => ({
        ...current,
        [user.id]: '',
      }))
      setMessage(`رمز کاربر ${user.username} بازنشانی شد.`)
    } catch (err) {
      setError(readError(err, 'خطا در بازنشانی رمز'))
    } finally {
      setBusy('')
    }
  }

  return (
    <>
      <PageHeader title="مدیریت کاربران" onBack={onBack} />

      {error && (
        <section className="error-box transfer-message">
          {error}
        </section>
      )}

      {message && (
        <section className="success-box transfer-message">
          {message}
        </section>
      )}

      <section className="welcome-card">
        <div className="section-title">
          <h3>ایجاد کاربر جدید</h3>
        </div>

        <form className="transfer-form" onSubmit={createUser}>
          <label>
            نام کاربری
            <input
              value={createForm.username}
              onChange={(event) =>
                setCreateForm((current) => ({
                  ...current,
                  username: event.target.value,
                }))
              }
              required
            />
          </label>

          <label>
            رمز عبور
            <input
              type="password"
              minLength="8"
              value={createForm.password}
              onChange={(event) =>
                setCreateForm((current) => ({
                  ...current,
                  password: event.target.value,
                }))
              }
              required
            />
          </label>

          <label>
            نقش
            <select
              value={createForm.role}
              onChange={(event) =>
                setCreateForm((current) => ({
                  ...current,
                  role: event.target.value,
                  warehouse_id:
                    event.target.value === 'admin'
                      ? ''
                      : current.warehouse_id,
                }))
              }
            >
              <option value="warehouse_manager">انباردار</option>
              <option value="admin">مدیر سامانه</option>
            </select>
          </label>

          {createForm.role === 'warehouse_manager' && (
            <label>
              انبار
              <select
                value={createForm.warehouse_id}
                onChange={(event) =>
                  setCreateForm((current) => ({
                    ...current,
                    warehouse_id: event.target.value,
                  }))
                }
                required
              >
                <option value="">انتخاب انبار</option>
                {warehouses.map((warehouse) => (
                  <option value={warehouse.id} key={warehouse.id}>
                    {warehouse.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          <button type="submit" disabled={busy === 'create'}>
            {busy === 'create'
              ? 'در حال ایجاد...'
              : 'ایجاد کاربر'}
          </button>
        </form>
      </section>

      <section className="welcome-card">
        <div className="section-title">
          <h3>کاربران سامانه</h3>
        </div>

        {loading ? (
          <p>در حال دریافت کاربران...</p>
        ) : (
          <div className="inventory-list">
            {users.map((user) => {
              const draft = drafts[user.id] || {}

              return (
                <article className="inventory-item" key={user.id}>
                  <div className="inventory-item-header">
                    <h3>{user.username}</h3>
                    <span>کاربر #{user.id}</span>
                  </div>

                  <div className="transfer-form">
                    <label>
                      نقش
                      <select
                        value={draft.role || ''}
                        onChange={(event) =>
                          updateDraft(
                            user.id,
                            'role',
                            event.target.value
                          )
                        }
                      >
                        <option value="warehouse_manager">
                          انباردار
                        </option>
                        <option value="admin">
                          مدیر سامانه
                        </option>
                      </select>
                    </label>

                    {draft.role === 'warehouse_manager' && (
                      <label>
                        انبار
                        <select
                          value={draft.warehouse_id || ''}
                          onChange={(event) =>
                            updateDraft(
                              user.id,
                              'warehouse_id',
                              event.target.value
                            )
                          }
                        >
                          <option value="">انتخاب انبار</option>
                          {warehouses.map((warehouse) => (
                            <option
                              value={warehouse.id}
                              key={warehouse.id}
                            >
                              {warehouse.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}

                    <label>
                      <span>
                        <input
                          type="checkbox"
                          checked={Boolean(draft.is_active)}
                          onChange={(event) =>
                            updateDraft(
                              user.id,
                              'is_active',
                              event.target.checked
                            )
                          }
                        />
                        {' '}کاربر فعال باشد
                      </span>
                    </label>

                    <button
                      type="button"
                      onClick={() => saveUser(user)}
                      disabled={busy === `save-${user.id}`}
                    >
                      ذخیره تغییرات
                    </button>

                    <label>
                      رمز عبور جدید
                      <input
                        type="password"
                        minLength="8"
                        value={passwords[user.id] || ''}
                        onChange={(event) =>
                          setPasswords((current) => ({
                            ...current,
                            [user.id]: event.target.value,
                          }))
                        }
                        placeholder="حداقل ۸ کاراکتر"
                      />
                    </label>

                    <button
                      type="button"
                      className="secondary-action-button"
                      onClick={() => resetPassword(user)}
                      disabled={busy === `password-${user.id}`}
                    >
                      بازنشانی رمز
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>
    </>
  )
}


function App() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const [token, setToken] = useState(localStorage.getItem('warehouse_token') || '')
  const [user, setUser] = useState(null)

  const [activePage, setActivePage] = useState('home')

  const [loading, setLoading] = useState(false)
  const [checkingSession, setCheckingSession] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const checkSession = async () => {
      if (!token) {
        setCheckingSession(false)
        return
      }

      try {
        const response = await apiClient.get('/auth/me')
        setUser(response.data)
      } catch {
        localStorage.removeItem('warehouse_token')
        setToken('')
        setUser(null)
      } finally {
        setCheckingSession(false)
      }
    }

    checkSession()
  }, [token])

  const handleLogin = async (event) => {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      const response = await apiClient.post('/auth/login', {
        username,
        password,
      })

      const accessToken = response.data.access_token

      localStorage.setItem('warehouse_token', accessToken)
      setToken(accessToken)

      const meResponse = await apiClient.get('/auth/me')
      setUser(meResponse.data)
      setActivePage('home')
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(detail || 'ورود ناموفق بود. نام کاربری یا رمز عبور را بررسی کنید.')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('warehouse_token')
    setToken('')
    setUser(null)
    setUsername('')
    setPassword('')
    setActivePage('home')
  }

  const goHome = () => {
    setActivePage('home')
  }

  if (checkingSession) {
    return (
      <main className="app-shell center-screen">
        <div className="card">
          <p className="muted">در حال بررسی نشست کاربر...</p>
        </div>
      </main>
    )
  }

  if (!user) {
    return (
      <main className="app-shell login-page">
        <section className="login-card">
          <div className="brand-box">
            <div className="brand-icon">ان</div>
            <div>
              <h1>سامانه هوشمند انبار</h1>
              <p>ورود امن کاربران انبار و مدیریت</p>
            </div>
          </div>

          <form onSubmit={handleLogin} className="login-form">
            <label>
              نام کاربری
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="مثلاً MH"
                required
              />
            </label>

            <label>
              رمز عبور
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="رمز عبور"
                required
              />
            </label>

            {error && <div className="error-box">{error}</div>}

            <button type="submit" disabled={loading}>
              {loading ? 'در حال ورود...' : 'ورود به سامانه'}
            </button>
          </form>
        </section>
      </main>
    )
  }

  return (
    <main className="app-shell dashboard-page">
      <header className="topbar">
        <div>
          <h1>سامانه هوشمند انبار</h1>
          <p>
            {user.role === 'admin' ? 'مدیر ارشد' : 'انباردار'}
            {user.warehouse_id ? ` | انبار ${user.warehouse_id}` : ''}
          </p>
        </div>

        <button className="ghost-button" onClick={handleLogout}>
          خروج
        </button>
      </header>

      {activePage === 'home' && (
        <>
          <section className="welcome-card">
            <h2>خوش آمدید، {user.username}</h2>
            <p>
              ورود موفق بود. از این پنل می‌توانید به بخش‌های موجودی، حواله،
              تاییدها، مغایرت، تولید و بسته‌بندی وارد شوید.
            </p>
          </section>

          <section className="menu-grid">
            <button className="menu-card" onClick={() => setActivePage('inventory')}>
              <span>📦</span>
              موجودی انبار
            </button>

            {user.role === 'admin' && (
              <button
                className="menu-card"
                onClick={() => setActivePage('inventoryExcel')}
              >
                <span>📊</span>
                ورود موجودی با Excel
              </button>
            )}

            <button className="menu-card" onClick={() => setActivePage('transfer')}>
              <span>🚚</span>
              ثبت حواله انتقال
            </button>

            <button className="menu-card" onClick={() => setActivePage('approvals')}>
              <span>✅</span>
              کارتابل حواله‌ها
            </button>

            <button className="menu-card" onClick={() => setActivePage('disputes')}>
              <span>⚠️</span>
              مغایرت و تیکت
            </button>

            <button className="menu-card" onClick={() => setActivePage('production')}>
              <span>🧪</span>
              تولید و فرمولاسیون
            </button>

            {user.role === 'admin' && (
              <button
                className="menu-card"
                onClick={() => setActivePage('users')}
              >
                <span>👥</span>
                مدیریت کاربران
              </button>
            )}
            <button className="menu-card" onClick={() => setActivePage('packaging')}>
              <span>🥡</span>
              بسته‌بندی و خسارت
            </button>
          </section>
        </>
      )}

      {activePage === 'inventory' && (
        <InventoryPage user={user} onBack={goHome} />
      )}

      {activePage === 'inventoryExcel' && user.role === 'admin' && (
        <InventoryExcelPage onBack={goHome} />
      )}

      {activePage === 'transfer' && (
        <TransferPage user={user} onBack={goHome} />
      )}

      {activePage === 'approvals' && (
        <ApprovalsPage user={user} onBack={goHome} />
      )}

      {activePage === 'disputes' && (
        <DisputesPage user={user} onBack={goHome} />
      )}

      {activePage === 'production' && (
        <ProductionPage
          user={user}
          onBack={goHome}
        />
      )}

      {activePage === 'users' && user.role === 'admin' && (
        <UserManagementPage onBack={goHome} />
      )}

      {activePage === 'packaging' && (
        <PackagingManagementPage
          user={user}
          onBack={goHome}
        />
      )}
    </main>
  )
}

export default App