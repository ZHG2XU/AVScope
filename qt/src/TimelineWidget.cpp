#include "TimelineWidget.h"

#include <QJsonObject>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QToolTip>

#include <algorithm>

TimelineWidget::TimelineWidget(QWidget *parent) : QWidget(parent)
{
    setMinimumHeight(220);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    setMouseTracking(true);
}

void TimelineWidget::setData(const QJsonArray &frames, const QJsonObject &summary)
{
    m_frames = frames;
    m_summary = summary;
    update();
}

void TimelineWidget::setDarkTheme(bool dark)
{
    m_dark = dark;
    update();
}

void TimelineWidget::paintEvent(QPaintEvent *)
{
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    const QColor background = m_dark ? QColor("#111820") : QColor("#FFFFFF");
    const QColor grid = m_dark ? QColor("#273442") : QColor("#DCE5EC");
    const QColor text = m_dark ? QColor("#9CACBA") : QColor("#566575");
    const QColor primary("#2F91C7");
    const QColor keyColor("#36B37E");
    const QColor ptsColor(m_dark ? "#73D2B3" : "#17785A");
    const QColor dtsColor(m_dark ? "#C5A3FF" : "#6641A5");
    const QColor bitrateColor(m_dark ? "#F5C567" : "#9A6700");
    const QColor anomalyColor("#EA5B62");
    painter.fillRect(rect(), background);

    const QRectF plot = rect().adjusted(38, 28, -18, -38);
    painter.setPen(QPen(grid, 1));
    for (int i = 0; i <= 4; ++i) {
        const qreal y = plot.top() + plot.height() * i / 4.0;
        painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y));
    }
    painter.setPen(text);
    painter.drawText(QRectF(12, 6, width() - 24, 20), Qt::AlignLeft,
                     tr("帧大小  PTS/DTS  码率  关键帧  异常"));

    if (m_frames.isEmpty()) {
        painter.drawText(plot, Qt::AlignCenter, tr("暂无可用帧数据"));
        return;
    }

    qint64 maxSize = 1;
    const int visible = qMin(m_frames.size(), 600);
    for (int i = 0; i < visible; ++i)
        maxSize = qMax(maxSize, static_cast<qint64>(m_frames.at(i).toObject().value("size").toDouble()));

    const qreal slot = plot.width() / qMax(1, visible);
    const qreal barWidth = qBound(1.5, slot * 0.68, 9.0);
    for (int i = 0; i < visible; ++i) {
        const auto frame = m_frames.at(i).toObject();
        const qreal ratio = frame.value("size").toDouble() / maxSize;
        const qreal h = qMax(2.0, plot.height() * ratio);
        const qreal x = plot.left() + slot * i + (slot - barWidth) / 2.0;
        painter.setPen(Qt::NoPen);
        painter.setBrush(frame.value("keyframe").toBool() ? keyColor : primary);
        painter.drawRoundedRect(QRectF(x, plot.bottom() - h, barWidth, h), 1.5, 1.5);
        if (frame.value("keyframe").toBool()) {
            QPolygonF marker;
            marker << QPointF(x + barWidth / 2, plot.top() - 2)
                   << QPointF(x + barWidth / 2 - 4, plot.top() - 10)
                   << QPointF(x + barWidth / 2 + 4, plot.top() - 10);
            painter.drawPolygon(marker);
        }
    }

    const auto series = m_summary.value("series").toArray();
    QVector<qreal> timestamps;
    for (const auto &pointValue : series) {
        const auto point = pointValue.toObject();
        if (point.value("pts").isDouble()) timestamps << point.value("pts").toDouble();
        if (point.value("dts").isDouble()) timestamps << point.value("dts").toDouble();
    }
    if (timestamps.size() >= 2) {
        const auto [minIt, maxIt] = std::minmax_element(timestamps.cbegin(), timestamps.cend());
        const qreal valueMin = *minIt;
        const qreal valueMax = *maxIt;
        const int points = qMin(series.size(), visible);
        if (valueMax > valueMin && points > 1) {
            for (const auto &spec : {qMakePair(QString("pts"), ptsColor), qMakePair(QString("dts"), dtsColor)}) {
                QPainterPath path;
                bool started = false;
                for (int i = 0; i < points; ++i) {
                    const auto value = series.at(i).toObject().value(spec.first);
                    if (!value.isDouble()) continue;
                    const qreal x = plot.left() + plot.width() * i / qMax(1, points - 1);
                    const qreal y = plot.bottom() - (value.toDouble() - valueMin) / (valueMax - valueMin) * plot.height();
                    if (!started) { path.moveTo(x, y); started = true; } else { path.lineTo(x, y); }
                }
                painter.setPen(QPen(spec.second, 1.8));
                painter.setBrush(Qt::NoBrush);
                painter.drawPath(path);
            }
        }
    }

    const auto buckets = m_summary.value("bitrate").toObject().value("buckets").toArray();
    qreal maxKbps = 0;
    for (const auto &value : buckets) maxKbps = qMax(maxKbps, value.toObject().value("kbps").toDouble());
    if (buckets.size() > 1 && maxKbps > 0) {
        QPainterPath path;
        for (int i = 0; i < buckets.size(); ++i) {
            const qreal x = plot.left() + plot.width() * i / qMax(1, buckets.size() - 1);
            const qreal y = plot.bottom() - buckets.at(i).toObject().value("kbps").toDouble() / maxKbps * plot.height();
            i == 0 ? path.moveTo(x, y) : path.lineTo(x, y);
        }
        painter.setPen(QPen(bitrateColor, 1.8));
        painter.drawPath(path);
    }

    const auto anomalies = m_summary.value("timestamp_anomalies").toArray();
    painter.setPen(Qt::NoPen);
    painter.setBrush(anomalyColor);
    for (const auto &value : anomalies) {
        const int order = value.toObject().value("item_order").toInt();
        if (order < 0 || order >= visible) continue;
        const qreal x = plot.left() + slot * order + slot / 2;
        painter.drawEllipse(QPointF(x, plot.top() + 5), 4, 4);
    }

    painter.setPen(text);
    painter.drawText(QRectF(plot.left(), plot.bottom() + 10, plot.width(), 20), Qt::AlignLeft,
                     tr("%1 帧  峰值 %2 B  关键帧 %3  时间戳异常 %4")
                         .arg(visible).arg(maxSize)
                         .arg(m_summary.value("gop").toObject().value("keyframes").toInt())
                         .arg(anomalies.size()));

    painter.setFont(QFont(painter.font().family(), 8));
    qreal legendX = plot.right() - 250;
    for (const auto &legend : {qMakePair(tr("PTS"), ptsColor), qMakePair(tr("DTS"), dtsColor),
                               qMakePair(tr("码率"), bitrateColor), qMakePair(tr("异常"), anomalyColor)}) {
        painter.setPen(QPen(legend.second, 2));
        painter.drawLine(QPointF(legendX, 16), QPointF(legendX + 14, 16));
        painter.setPen(text);
        painter.drawText(QPointF(legendX + 18, 20), legend.first);
        legendX += 58;
    }
}

int TimelineWidget::frameAtPosition(qreal x) const
{
    const QRectF plot = rect().adjusted(38, 28, -18, -38);
    if (!plot.contains(QPointF(x, plot.center().y())) || m_frames.isEmpty()) return -1;
    const int visible = qMin(m_frames.size(), 600);
    return qBound(0, static_cast<int>((x - plot.left()) / plot.width() * visible), visible - 1);
}

void TimelineWidget::mouseMoveEvent(QMouseEvent *event)
{
    const int row = frameAtPosition(event->position().x());
    if (row < 0) return;
    const auto frame = m_frames.at(row).toObject();
    setToolTip(tr("帧 #%1\nOffset 0x%2\nSize %3 B\nPTS %4  DTS %5\n类型 %6")
                   .arg(frame.value("index").toInt())
                   .arg(static_cast<qint64>(frame.value("offset").toDouble()), 0, 16)
                   .arg(static_cast<qint64>(frame.value("size").toDouble()))
                   .arg(frame.value("pts").toVariant().toString())
                   .arg(frame.value("dts").toVariant().toString())
                   .arg(frame.value("frame_type").toString()));
    QWidget::mouseMoveEvent(event);
}

void TimelineWidget::mousePressEvent(QMouseEvent *event)
{
    const int row = frameAtPosition(event->position().x());
    if (row >= 0) emit frameSelected(row);
    QWidget::mousePressEvent(event);
}
