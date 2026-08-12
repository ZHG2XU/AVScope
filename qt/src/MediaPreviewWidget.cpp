#include "MediaPreviewWidget.h"

#include <QFileInfo>
#include <QJsonArray>
#include <QPainter>
#include <QPainterPath>

namespace {
QColor blend(const QColor &left, const QColor &right, qreal amount)
{
    return QColor::fromRgbF(
        left.redF() * (1.0 - amount) + right.redF() * amount,
        left.greenF() * (1.0 - amount) + right.greenF() * amount,
        left.blueF() * (1.0 - amount) + right.blueF() * amount);
}

QString scalarText(const QJsonValue &value)
{
    if (value.isString()) return value.toString();
    if (value.isDouble()) return QString::number(value.toDouble(), 'g', 8);
    if (value.isBool()) return value.toBool() ? QObject::tr("是") : QObject::tr("否");
    return {};
}
}

MediaPreviewWidget::MediaPreviewWidget(QWidget *parent) : QWidget(parent)
{
    setMinimumSize(480, 320);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
}

void MediaPreviewWidget::setMedia(const QJsonObject &media)
{
    m_media = media;
    m_summary = media.value("summary").toObject();
    loadVisual();
    update();
}

void MediaPreviewWidget::setDarkTheme(bool dark)
{
    m_dark = dark;
    update();
}

void MediaPreviewWidget::loadVisual()
{
    m_image = {};
    for (const QString &key : {QString("video_preview"), QString("yuv_preview")}) {
        const auto preview = m_summary.value(key).toObject();
        const QString path = preview.value("path").toString();
        if (preview.value("available").toBool() && QFileInfo::exists(path) && m_image.load(path))
            return;
    }
}

void MediaPreviewWidget::paintEvent(QPaintEvent *)
{
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.setRenderHint(QPainter::SmoothPixmapTransform);

    const QColor background = m_dark ? QColor("#121A22") : QColor("#FFFFFF");
    const QColor surface = m_dark ? QColor("#17212B") : QColor("#EDF2F6");
    const QColor text = m_dark ? QColor("#E7EDF3") : QColor("#172331");
    const QColor muted = m_dark ? QColor("#94A3B2") : QColor("#607080");
    const QColor border = m_dark ? QColor("#273442") : QColor("#D8E1E8");
    painter.fillRect(rect(), background);

    const QRectF content = QRectF(rect()).adjusted(24, 20, -24, -20);
    QFont titleFont = font();
    titleFont.setPointSize(15);
    titleFont.setBold(true);
    painter.setFont(titleFont);
    painter.setPen(text);
    painter.drawText(content.left(), content.top() + 20, m_media.value("format_name").toString(tr("媒体预览")));

    QFont captionFont = font();
    captionFont.setPointSize(9);
    painter.setFont(captionFont);
    painter.setPen(muted);
    painter.drawText(content.left(), content.top() + 43, visualCaption());

    QRectF visualArea(content.left(), content.top() + 62, content.width(), qMax<qreal>(150, content.height() * 0.57));
    QPainterPath panelPath;
    panelPath.addRoundedRect(visualArea, 6, 6);
    painter.fillPath(panelPath, surface);
    painter.setPen(QPen(border, 1));
    painter.drawPath(panelPath);

    if (!m_image.isNull()) {
        const QSizeF fitted = m_image.size().scaled(visualArea.size().toSize() - QSize(30, 30), Qt::KeepAspectRatio);
        const QRectF target(visualArea.center().x() - fitted.width() / 2.0,
                            visualArea.center().y() - fitted.height() / 2.0,
                            fitted.width(), fitted.height());
        painter.drawImage(target, m_image);
    } else if (m_summary.value("waveform").toObject().value("available").toBool()) {
        drawWaveform(painter, visualArea.adjusted(18, 16, -18, -16));
    } else {
        painter.setPen(muted);
        painter.drawText(visualArea, Qt::AlignCenter, tr("当前文件没有可解码画面或音频波形"));
    }

    const QRectF summaryArea(content.left(), visualArea.bottom() + 18, content.width(),
                             qMax<qreal>(72, content.bottom() - visualArea.bottom() - 18));
    drawSummary(painter, summaryArea);
}

void MediaPreviewWidget::drawWaveform(QPainter &painter, const QRectF &area) const
{
    const auto waveform = m_summary.value("waveform").toObject();
    const auto peaks = waveform.value("peaks").toArray();
    if (peaks.isEmpty()) return;

    const QColor grid = m_dark ? QColor("#2A3947") : QColor("#CFDAE3");
    const QColor axis = m_dark ? QColor("#637486") : QColor("#91A1B1");
    const QColor peak = QColor("#36A7D8");
    const QColor rms = m_dark ? QColor("#73D2B3") : QColor("#17785A");
    painter.setPen(QPen(grid, 1));
    for (int index = 1; index < 4; ++index) {
        const qreal y = area.top() + area.height() * index / 4.0;
        painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y));
    }
    painter.setPen(QPen(axis, 1.2));
    painter.drawLine(QPointF(area.left(), area.center().y()), QPointF(area.right(), area.center().y()));

    const qreal step = area.width() / qMax(1, peaks.size());
    for (int index = 0; index < peaks.size(); ++index) {
        const auto point = peaks.at(index).toObject();
        const qreal x = area.left() + (index + 0.5) * step;
        const qreal high = area.center().y() - point.value("max").toDouble() * area.height() * 0.46;
        const qreal low = area.center().y() - point.value("min").toDouble() * area.height() * 0.46;
        painter.setPen(QPen(peak, qMax<qreal>(1.2, step * 0.55), Qt::SolidLine, Qt::RoundCap));
        painter.drawLine(QPointF(x, high), QPointF(x, low));
        const qreal rmsHeight = point.value("rms").toDouble() * area.height() * 0.46;
        painter.setPen(QPen(rms, qMax<qreal>(0.8, step * 0.22), Qt::SolidLine, Qt::RoundCap));
        painter.drawLine(QPointF(x, area.center().y() - rmsHeight), QPointF(x, area.center().y() + rmsHeight));
    }
}

void MediaPreviewWidget::drawSummary(QPainter &painter, const QRectF &area) const
{
    const QColor surface = m_dark ? QColor("#17212B") : QColor("#EDF2F6");
    const QColor text = m_dark ? QColor("#E7EDF3") : QColor("#172331");
    const QColor muted = m_dark ? QColor("#94A3B2") : QColor("#607080");
    QStringList keys = {"width", "height", "pixel_format", "fps", "sample_rate", "channels", "bits_per_sample", "duration"};
    QStringList labels = {tr("宽度"), tr("高度"), tr("像素格式"), tr("帧率"), tr("采样率"), tr("声道"), tr("位深"), tr("时长")};
    QVector<QPair<QString, QString>> values;
    for (int index = 0; index < keys.size(); ++index) {
        const QString value = scalarText(m_summary.value(keys.at(index)));
        if (!value.isEmpty()) values.append({labels.at(index), value});
    }
    const auto energy = m_summary.value("waveform").toObject().value("energy").toObject();
    if (!energy.isEmpty()) {
        values.append({"Peak", QString("%1 dBFS").arg(energy.value("peak_dbfs").toDouble(), 0, 'f', 2)});
        values.append({"RMS", QString("%1 dBFS").arg(energy.value("rms_dbfs").toDouble(), 0, 'f', 2)});
    }
    if (values.isEmpty()) values.append({tr("文件大小"), QString::number(m_media.value("size").toDouble()) + " B"});

    const int columns = qMin(4, values.size());
    const qreal gap = 10;
    const qreal cardWidth = (area.width() - gap * (columns - 1)) / columns;
    const qreal cardHeight = qMin<qreal>(72, area.height());
    QFont labelFont = font();
    labelFont.setPointSize(8);
    QFont valueFont = font();
    valueFont.setPointSize(11);
    valueFont.setBold(true);
    for (int index = 0; index < columns; ++index) {
        const QRectF card(area.left() + index * (cardWidth + gap), area.top(), cardWidth, cardHeight);
        painter.setPen(Qt::NoPen);
        painter.setBrush(surface);
        painter.drawRoundedRect(card, 5, 5);
        painter.setFont(labelFont);
        painter.setPen(muted);
        painter.drawText(card.adjusted(12, 9, -8, -8), Qt::AlignTop | Qt::AlignLeft, values.at(index).first);
        painter.setFont(valueFont);
        painter.setPen(text);
        painter.drawText(card.adjusted(12, 27, -8, -7), Qt::AlignTop | Qt::AlignLeft, values.at(index).second);
    }
}

QString MediaPreviewWidget::visualCaption() const
{
    if (!m_image.isNull()) {
        const auto preview = m_summary.value("video_preview").toObject().value("available").toBool()
            ? m_summary.value("video_preview").toObject() : m_summary.value("yuv_preview").toObject();
        return tr("%1 × %2  %3").arg(preview.value("width").toInt()).arg(preview.value("height").toInt())
            .arg(preview.value("pixel_format").toString());
    }
    const auto waveform = m_summary.value("waveform").toObject();
    if (waveform.value("available").toBool())
        return tr("音频波形  %1 Hz  %2 声道").arg(waveform.value("sample_rate").toInt()).arg(waveform.value("channels").toInt());
    return tr("结构化媒体摘要");
}
