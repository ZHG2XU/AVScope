#include "TimelineWidget.h"

#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QToolTip>
#include <QWheelEvent>

#include <algorithm>

TimelineWidget::TimelineWidget(QWidget *parent) : QWidget(parent)
{
    setMinimumHeight(220);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    setMouseTracking(true);
    setFocusPolicy(Qt::StrongFocus);
}

void TimelineWidget::setData(const QJsonArray &frames, const QJsonObject &summary)
{
    m_frames = frames;
    m_summary = summary;
    m_items = frames.isEmpty() ? summary.value("series").toArray() : frames;
    m_visibleStart = 0;
    m_visibleCount = qMin(itemCount(), 240);
    m_selectedItem = -1;
    m_currentAnomaly = -1;
    normalizeRange();
    emit rangeChanged(rangeText());
    update();
}

void TimelineWidget::setDarkTheme(bool dark)
{
    m_dark = dark;
    update();
}

int TimelineWidget::itemCount() const
{
    return m_items.size();
}

QJsonObject TimelineWidget::itemAt(int index) const
{
    return index >= 0 && index < m_items.size() ? m_items.at(index).toObject() : QJsonObject{};
}

void TimelineWidget::normalizeRange()
{
    if (itemCount() <= 0) {
        m_visibleStart = 0;
        m_visibleCount = 0;
        return;
    }
    const int minimumVisible = qMin(8, itemCount());
    m_visibleCount = qBound(minimumVisible, m_visibleCount <= 0 ? qMin(itemCount(), 240) : m_visibleCount, itemCount());
    m_visibleStart = qBound(0, m_visibleStart, qMax(0, itemCount() - m_visibleCount));
}

QString TimelineWidget::rangeText() const
{
    if (itemCount() <= 0) return tr("无时间线数据");
    return tr("可见 %1-%2 / 共 %3 项")
        .arg(m_visibleStart + 1).arg(m_visibleStart + m_visibleCount).arg(itemCount());
}

void TimelineWidget::zoomBy(qreal factor)
{
    if (itemCount() <= 0 || factor <= 0) return;
    const int center = m_visibleStart + m_visibleCount / 2;
    m_visibleCount = qBound(qMin(8, itemCount()), qRound(m_visibleCount * factor), itemCount());
    m_visibleStart = center - m_visibleCount / 2;
    normalizeRange();
    emit rangeChanged(rangeText());
    update();
}

void TimelineWidget::panBy(int direction)
{
    if (itemCount() <= 0) return;
    m_visibleStart += direction * qMax(1, m_visibleCount / 4);
    normalizeRange();
    emit rangeChanged(rangeText());
    update();
}

void TimelineWidget::resetView()
{
    m_visibleStart = 0;
    m_visibleCount = qMin(itemCount(), 240);
    normalizeRange();
    emit rangeChanged(rangeText());
    update();
}

void TimelineWidget::navigateAnomaly(int direction)
{
    const auto anomalies = m_summary.value("timestamp_anomalies").toArray();
    if (anomalies.isEmpty()) return;
    m_currentAnomaly = (m_currentAnomaly + direction + anomalies.size()) % anomalies.size();
    const int item = anomalies.at(m_currentAnomaly).toObject().value("item_order").toInt(-1);
    if (item < 0 || item >= itemCount()) return;
    if (item < m_visibleStart || item >= m_visibleStart + m_visibleCount)
        m_visibleStart = item - m_visibleCount / 2;
    normalizeRange();
    setSelectedItem(item);
    emit rangeChanged(tr("异常 %1 / %2  ·  %3").arg(m_currentAnomaly + 1).arg(anomalies.size()).arg(rangeText()));
}

void TimelineWidget::selectItem(int index)
{
    if (index < 0 || index >= itemCount()) return;
    m_selectedItem = index;
    if (index < m_visibleStart || index >= m_visibleStart + m_visibleCount) {
        m_visibleStart = index - m_visibleCount / 2;
        normalizeRange();
        emit rangeChanged(rangeText());
    }
    update();
}

void TimelineWidget::paintEvent(QPaintEvent *)
{
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    const QColor background = m_dark ? QColor("#111820") : QColor("#FFFFFF");
    const QColor grid = m_dark ? QColor("#273442") : QColor("#DCE5EC");
    const QColor text = m_dark ? QColor("#AAB8C5") : QColor("#4E6070");
    const QColor primary(m_dark ? "#54B4E8" : "#1777A8");
    const QColor keyColor(m_dark ? "#54D39A" : "#17785A");
    const QColor ptsColor(m_dark ? "#73D2B3" : "#17785A");
    const QColor dtsColor(m_dark ? "#C5A3FF" : "#6641A5");
    const QColor bitrateColor(m_dark ? "#F5C567" : "#8A5A00");
    const QColor anomalyColor(m_dark ? "#FF747C" : "#B4232F");
    const QColor cursorColor(m_dark ? "#FFFFFF" : "#172331");
    painter.fillRect(rect(), background);

    const QRectF plot = rect().adjusted(42, 32, -18, -42);
    painter.setPen(QPen(grid, 1));
    for (int i = 0; i <= 4; ++i) {
        const qreal y = plot.top() + plot.height() * i / 4.0;
        painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y));
    }
    painter.setPen(text);
    painter.drawText(QRectF(12, 7, width() - 24, 20), Qt::AlignLeft,
                     tr("帧/包大小  ·  PTS/DTS  ·  码率  ·  关键帧  ·  时间戳异常"));

    if (itemCount() <= 0) {
        painter.drawText(plot, Qt::AlignCenter, tr("当前文件没有可绘制的帧或数据包时间线"));
        return;
    }

    qint64 maxSize = 1;
    for (int i = m_visibleStart; i < m_visibleStart + m_visibleCount; ++i)
        maxSize = qMax(maxSize, static_cast<qint64>(itemAt(i).value("size").toDouble()));

    const qreal slot = plot.width() / qMax(1, m_visibleCount);
    const qreal barWidth = qBound(1.5, slot * 0.68, 10.0);
    for (int visible = 0; visible < m_visibleCount; ++visible) {
        const int index = m_visibleStart + visible;
        const auto item = itemAt(index);
        const qreal ratio = item.value("size").toDouble() / maxSize;
        const qreal height = qMax(2.0, plot.height() * ratio);
        const qreal x = plot.left() + slot * visible + (slot - barWidth) / 2.0;
        painter.setPen(Qt::NoPen);
        painter.setBrush(item.value("keyframe").toBool() ? keyColor : primary);
        painter.drawRoundedRect(QRectF(x, plot.bottom() - height, barWidth, height), 1.5, 1.5);
        if (item.value("keyframe").toBool()) {
            painter.setBrush(keyColor);
            painter.drawEllipse(QPointF(x + barWidth / 2, plot.top() + 4), 3.2, 3.2);
        }
    }

    QVector<qreal> timestamps;
    for (int i = m_visibleStart; i < m_visibleStart + m_visibleCount; ++i) {
        const auto point = itemAt(i);
        if (point.value("pts").isDouble()) timestamps << point.value("pts").toDouble();
        if (point.value("dts").isDouble()) timestamps << point.value("dts").toDouble();
    }
    if (timestamps.size() >= 2) {
        const auto bounds = std::minmax_element(timestamps.cbegin(), timestamps.cend());
        if (*bounds.second > *bounds.first) {
            for (const auto &spec : {qMakePair(QString("pts"), ptsColor), qMakePair(QString("dts"), dtsColor)}) {
                QPainterPath path;
                bool started = false;
                for (int i = 0; i < m_visibleCount; ++i) {
                    const int index = m_visibleStart + i;
                    const auto value = itemAt(index).value(spec.first);
                    if (!value.isDouble()) continue;
                    const qreal x = plot.left() + slot * (i + 0.5);
                    const qreal y = plot.bottom() - (value.toDouble() - *bounds.first) / (*bounds.second - *bounds.first) * plot.height();
                    started ? path.lineTo(x, y) : path.moveTo(x, y);
                    started = true;
                }
                painter.setPen(QPen(spec.second, 1.8));
                painter.setBrush(Qt::NoBrush);
                painter.drawPath(path);
            }
        }
    }

    const auto buckets = m_summary.value("bitrate").toObject().value("buckets").toArray();
    if (buckets.size() > 1) {
        const int bucketStart = qBound(0, m_visibleStart * buckets.size() / qMax(1, itemCount()), buckets.size() - 1);
        const int bucketEnd = qBound(bucketStart + 1,
            (m_visibleStart + m_visibleCount) * buckets.size() / qMax(1, itemCount()), buckets.size());
        qreal maxKbps = 0;
        for (int i = bucketStart; i < bucketEnd; ++i)
            maxKbps = qMax(maxKbps, buckets.at(i).toObject().value("kbps").toDouble());
        if (maxKbps > 0) {
            QPainterPath bitratePath;
            for (int i = bucketStart; i < bucketEnd; ++i) {
                const qreal x = plot.left() + plot.width() * (i - bucketStart) / qMax(1, bucketEnd - bucketStart - 1);
                const qreal y = plot.bottom() - buckets.at(i).toObject().value("kbps").toDouble() / maxKbps * plot.height();
                i == bucketStart ? bitratePath.moveTo(x, y) : bitratePath.lineTo(x, y);
            }
            painter.setPen(QPen(bitrateColor, 1.8));
            painter.setBrush(Qt::NoBrush);
            painter.drawPath(bitratePath);
        }
    }

    const auto anomalies = m_summary.value("timestamp_anomalies").toArray();
    painter.setPen(Qt::NoPen);
    painter.setBrush(anomalyColor);
    for (const auto &value : anomalies) {
        const int item = value.toObject().value("item_order").toInt(-1);
        if (item < m_visibleStart || item >= m_visibleStart + m_visibleCount) continue;
        const qreal x = plot.left() + slot * (item - m_visibleStart + 0.5);
        painter.drawEllipse(QPointF(x, plot.top() + 10), 4, 4);
    }

    if (m_selectedItem >= m_visibleStart && m_selectedItem < m_visibleStart + m_visibleCount) {
        const qreal x = plot.left() + slot * (m_selectedItem - m_visibleStart + 0.5);
        painter.setPen(QPen(cursorColor, 1.4));
        painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()));
    }

    painter.setPen(text);
    painter.drawText(QRectF(plot.left(), plot.bottom() + 10, plot.width(), 22), Qt::AlignLeft,
                     tr("%1  ·  峰值 %2 B  ·  关键帧 %3  ·  异常 %4")
                         .arg(rangeText()).arg(maxSize)
                         .arg(m_summary.value("gop").toObject().value("keyframes").toInt())
                         .arg(anomalies.size()));

    qreal legendX = qMax(plot.left() + 280, plot.right() - 232);
    for (const auto &legend : {qMakePair(tr("PTS"), ptsColor), qMakePair(tr("DTS"), dtsColor),
                               qMakePair(tr("码率"), bitrateColor), qMakePair(tr("异常"), anomalyColor)}) {
        painter.setPen(QPen(legend.second, 2));
        painter.drawLine(QPointF(legendX, 17), QPointF(legendX + 13, 17));
        painter.setPen(text);
        painter.drawText(QPointF(legendX + 17, 21), legend.first);
        legendX += 54;
    }
}

int TimelineWidget::itemAtPosition(qreal x) const
{
    const QRectF plot = rect().adjusted(42, 32, -18, -42);
    if (x < plot.left() || x > plot.right() || m_visibleCount <= 0) return -1;
    const int visible = qBound(0, static_cast<int>((x - plot.left()) / plot.width() * m_visibleCount), m_visibleCount - 1);
    return m_visibleStart + visible;
}

void TimelineWidget::setSelectedItem(int index, bool activate)
{
    if (index < 0 || index >= itemCount()) return;
    m_selectedItem = index;
    update();
    if (index < m_frames.size()) {
        emit frameSelected(index);
        if (activate) emit frameActivated(index);
    }
}

void TimelineWidget::mouseMoveEvent(QMouseEvent *event)
{
    const int index = itemAtPosition(event->position().x());
    if (index >= 0) {
        const auto item = itemAt(index);
        setToolTip(tr("项目 #%1\nOffset 0x%2\nSize %3 B\nPTS %4  DTS %5\n类型 %6")
            .arg(item.value("index").toVariant().toString())
            .arg(static_cast<qint64>(item.value("offset").toDouble()), 0, 16)
            .arg(static_cast<qint64>(item.value("size").toDouble()))
            .arg(item.value("pts").toVariant().toString())
            .arg(item.value("dts").toVariant().toString())
            .arg(item.value("frame_type").toString(item.value("kind").toString())));
    }
    QWidget::mouseMoveEvent(event);
}

void TimelineWidget::mousePressEvent(QMouseEvent *event)
{
    if (event->button() == Qt::LeftButton)
        setSelectedItem(itemAtPosition(event->position().x()));
    QWidget::mousePressEvent(event);
}

void TimelineWidget::mouseDoubleClickEvent(QMouseEvent *event)
{
    if (event->button() == Qt::LeftButton)
        setSelectedItem(itemAtPosition(event->position().x()), true);
    QWidget::mouseDoubleClickEvent(event);
}

void TimelineWidget::wheelEvent(QWheelEvent *event)
{
    if (event->modifiers().testFlag(Qt::ShiftModifier))
        panBy(event->angleDelta().y() > 0 ? -1 : 1);
    else
        zoomBy(event->angleDelta().y() > 0 ? 0.75 : 1.35);
    event->accept();
}
