import { useState } from 'react'
import { apiClient } from './api/client'


function getErrorMessage(error) {
  const detail = error?.response?.data?.detail

  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message

  return 'عملیات انجام نشد. فایل و ارتباط با سرور را بررسی کنید.'
}


function SummaryCard({ title, value }) {
  return (
    <div className="summary-card">
      <span>{title}</span>
      <strong>{Number(value || 0).toLocaleString('fa-IR')}</strong>
    </div>
  )
}


function InventoryExcelPage({ onBack }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const resetResult = () => {
    setPreview(null)
    setError('')
    setSuccess('')
  }

  const handleFileChange = (event) => {
    const selectedFile = event.target.files?.[0] || null

    resetResult()
    setFile(selectedFile)

    if (
      selectedFile &&
      !selectedFile.name.toLowerCase().endsWith('.xlsx')
    ) {
      setError('فقط فایل Excel با پسوند xlsx مجاز است.')
      setFile(null)
      event.target.value = ''
    }
  }

  const downloadTemplate = async () => {
    setLoading('template')
    setError('')
    setSuccess('')

    try {
      const response = await apiClient.get(
        '/admin-panel/inventory-excel/template',
        { responseType: 'blob' },
      )

      const url = window.URL.createObjectURL(response.data)
      const link = document.createElement('a')

      link.href = url
      link.download = 'initial_inventory_template.xlsx'
      document.body.appendChild(link)
      link.click()
      link.remove()

      window.URL.revokeObjectURL(url)
      setSuccess('فایل نمونه با موفقیت دریافت شد.')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading('')
    }
  }

  const previewFile = async () => {
    if (!file) {
      setError('ابتدا فایل Excel را انتخاب کنید.')
      return
    }

    setLoading('preview')
    setError('')
    setSuccess('')
    setPreview(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await apiClient.post(
        '/admin-panel/inventory-excel/preview',
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        },
      )

      setPreview(response.data)

      if (response.data.valid) {
        setSuccess(
          'فایل معتبر است. اطلاعات زیر را بررسی و سپس ثبت نهایی کنید.',
        )
      } else {
        setError(
          'فایل دارای خطا است. هیچ اطلاعاتی در سامانه ثبت نشده است.',
        )
      }
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading('')
    }
  }

  const commitFile = async () => {
    if (!file || !preview?.valid) {
      setError('ابتدا پیش‌نمایش موفق فایل را انجام دهید.')
      return
    }

    const confirmed = window.confirm(
      'موجودی‌های این فایل ثبت یا به‌روزرسانی شوند؟',
    )

    if (!confirmed) return

    setLoading('commit')
    setError('')
    setSuccess('')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await apiClient.post(
        '/admin-panel/inventory-excel/commit',
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        },
      )

      setSuccess(
        response.data.message || 'اطلاعات با موفقیت ثبت شد.',
      )

      setPreview({
        valid: true,
        summary: response.data.summary,
        errors: [],
        preview_rows: [],
      })
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading('')
    }
  }

  const summary = preview?.summary || {}

  return (
    <>
      <div className="page-header">
        <button className="ghost-button" onClick={onBack}>
          بازگشت
        </button>
        <h2>ورود موجودی با Excel</h2>
      </div>

      <section className="welcome-card">
        <h2>ثبت موجودی اولیه</h2>
        <p>
          ابتدا فایل نمونه را دریافت کنید، اطلاعات را بدون تغییر عنوان
          ستون‌ها تکمیل کنید و سپس فایل را برای بررسی بارگذاری کنید.
        </p>
      </section>

      <section className="excel-import-card">
        <button
          type="button"
          className="secondary-action-button"
          onClick={downloadTemplate}
          disabled={Boolean(loading)}
        >
          {loading === 'template'
            ? 'در حال دریافت...'
            : 'دریافت فایل نمونه Excel'}
        </button>

        <label className="excel-file-label">
          انتخاب فایل تکمیل‌شده
          <input
            type="file"
            accept=".xlsx"
            onChange={handleFileChange}
            disabled={Boolean(loading)}
          />
        </label>

        {file && (
          <div className="selected-file-box">
            فایل انتخاب‌شده: <strong>{file.name}</strong>
          </div>
        )}

        <button
          type="button"
          onClick={previewFile}
          disabled={!file || Boolean(loading)}
        >
          {loading === 'preview'
            ? 'در حال بررسی فایل...'
            : 'بررسی و پیش‌نمایش'}
        </button>
      </section>

      {error && <section className="error-box">{error}</section>}
      {success && <section className="success-box">{success}</section>}

      {preview && (
        <>
          <section className="summary-row excel-summary-row">
            <SummaryCard
              title="ردیف‌های کالا"
              value={summary.inventory_rows}
            />
            <SummaryCard
              title="ردیف‌های بسته‌بندی"
              value={summary.packaging_rows}
            />
            <SummaryCard
              title="کالای جدید"
              value={summary.new_products}
            />
            <SummaryCard
              title="بچ جدید"
              value={summary.new_batches}
            />
            <SummaryCard
              title="موجودی جدید"
              value={summary.inventory_creates}
            />
            <SummaryCard
              title="موجودی به‌روزرسانی"
              value={summary.inventory_updates}
            />
            <SummaryCard
              title="بسته‌بندی جدید"
              value={summary.packaging_creates}
            />
            <SummaryCard
              title="تعداد خطا"
              value={summary.error_count}
            />
          </section>

          {preview.errors?.length > 0 && (
            <section className="excel-error-list">
              <h3>خطاهای فایل</h3>

              {preview.errors.map((item, index) => (
                <div
                  className="excel-error-item"
                  key={`${item.sheet}-${item.row}-${index}`}
                >
                  <strong>
                    {item.sheet}
                    {item.row ? `، ردیف ${item.row}` : ''}
                  </strong>
                  <span>{item.message}</span>
                </div>
              ))}
            </section>
          )}

          {preview.valid && (
            <section className="excel-final-action">
              <p>
                پیش‌نمایش موفق بود. با ثبت نهایی، موجودی‌های جدید ساخته
                و موجودی‌های تکراری به‌روزرسانی می‌شوند.
              </p>

              <button
                type="button"
                onClick={commitFile}
                disabled={Boolean(loading)}
              >
                {loading === 'commit'
                  ? 'در حال ثبت نهایی...'
                  : 'ثبت نهایی موجودی‌ها'}
              </button>
            </section>
          )}
        </>
      )}
    </>
  )
}


export default InventoryExcelPage