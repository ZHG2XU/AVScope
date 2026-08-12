#include "TimelineWidget.h"

#include <QJsonObject>
#include <QPainter>
#include <QPainterPath>

TimelineWidget::TimelineWidget(QWidget *parent) : QWidget(parent)
{
    setMinimumHeight(220);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
}

void TimelineWidget::setFrames(const QJsonArray &frames)
{
    m_frames = frames;
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
    painter.fillRect(rect(), background);

    const QRectF plot = rect().adjusted(38, 28, -18, -38);
    painter.setPen(QPen(grid, 1));
    for (int i = 0; i <= 4; ++i) {
        const qreal y = plot.top() + plot.height() * i / 4.0;
        painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y));
    }
    painter.setPen(text);
    painter.drawText(QRectF(12, 6, width() - 24, 20), Qt::AlignLeft, tr("帧大小分布 / Frame size distribution"));

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
    }

    painter.setPen(text);
    painter.drawText(QRectF(plot.left(), plot.bottom() + 10, plot.width(), 20), Qt::AlignLeft,
                     tr("%1 帧   峰值 %2 bytes").arg(visible).arg(maxSize));
}
