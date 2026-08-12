#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QWidget>

class TimelineWidget final : public QWidget
{
    Q_OBJECT
public:
    explicit TimelineWidget(QWidget *parent = nullptr);
    void setData(const QJsonArray &frames, const QJsonObject &summary);
    void setDarkTheme(bool dark);

signals:
    void frameSelected(int row);

protected:
    void paintEvent(QPaintEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;

private:
    int frameAtPosition(qreal x) const;
    QJsonArray m_frames;
    QJsonObject m_summary;
    bool m_dark = true;
};
