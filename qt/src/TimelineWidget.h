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
    void zoomBy(qreal factor);
    void panBy(int direction);
    void resetView();
    void navigateAnomaly(int direction);
    void selectItem(int index);
    QString rangeText() const;

signals:
    void frameSelected(int row);
    void frameActivated(int row);
    void rangeChanged(const QString &text);

protected:
    void paintEvent(QPaintEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseDoubleClickEvent(QMouseEvent *event) override;
    void wheelEvent(QWheelEvent *event) override;

private:
    int itemAtPosition(qreal x) const;
    int itemCount() const;
    QJsonObject itemAt(int index) const;
    void setSelectedItem(int index, bool activate = false);
    void normalizeRange();

    QJsonArray m_frames;
    QJsonArray m_items;
    QJsonObject m_summary;
    int m_visibleStart = 0;
    int m_visibleCount = 0;
    int m_selectedItem = -1;
    int m_currentAnomaly = -1;
    bool m_dark = true;
};
