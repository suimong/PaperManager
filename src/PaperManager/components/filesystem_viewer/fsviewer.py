import pathlib

from PyQt6.QtWidgets import (
    QDockWidget,
    QTreeView,
    QHeaderView,
    QLineEdit,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QSizePolicy,
    QFrame,
    QHBoxLayout,
    QLabel,
)
from PyQt6.QtGui import QFileSystemModel, QColor
from PyQt6.QtCore import QDir, Qt, QModelIndex

from ..signals import PMCommunicate


class FSTreeView(QTreeView):
    def __init__(self, parent, comm: PMCommunicate) -> None:
        super().__init__(parent)
        self.comm = comm

    def currentChanged(self, current, previous):
        if not current:
            return
        selected_file_path = self.model().filePath(current)
        self.comm.open_pdf.emit(selected_file_path)
        super().currentChanged(current, previous)


class FSModel(QFileSystemModel):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        # Show only PDF files
        self.setNameFilters(["*.pdf", "*.PDF"])
        self.setNameFilterDisables(False)

    def columnCount(self, parent=QModelIndex()):
        # Add one more column for tags
        return super().columnCount(parent) + 1

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and section == self.columnCount() - 1
        ):
            return "Tags"
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        isTagCol = False
        if index.isValid():
            isTagCol = index.column() == self.columnCount(index.parent()) - 1
            info = self.fileInfo(index)
            path = info.absoluteFilePath()
            if path:
                if isTagCol:
                    if role == Qt.ItemDataRole.DecorationRole:
                        pass
                    elif role == Qt.ItemDataRole.DisplayRole:
                        return f"JFE; Open Access;"
                    elif role == Qt.ItemDataRole.ForegroundRole:
                        return QColor("blue")
        if not isTagCol:
            return super().data(index, role)


class TagBar(QWidget):
    # https://robonobodojo.wordpress.com/2018/09/11/creating-a-tag-bar-in-pyside/

    def __init__(self, parent, comm: PMCommunicate):
        super().__init__(parent)
        self.comm = comm
        self.tags = []
        self.h_layout = QHBoxLayout()
        self.h_layout.setSpacing(4)
        self.setLayout(self.h_layout)
        self.line_edit = QLineEdit()
        self.line_edit.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Maximum
        )
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.setContentsMargins(2, 2, 2, 2)
        self.h_layout.setContentsMargins(2, 2, 2, 2)
        self.refresh()
        self.setup_ui()
        self.show()

    def setup_ui(self):
        self.line_edit.returnPressed.connect(self.create_tags)

    def create_tags(self):
        if self.line_edit.text():
            new_tags = self.line_edit.text().split(", ")
        else:
            new_tags = []
        self.line_edit.setText("")
        self.tags.extend(new_tags)
        self.tags = list(set(self.tags))
        self.tags.sort(key=lambda x: x.lower())
        self.refresh()

    def refresh(self):
        for i in reversed(range(self.h_layout.count())):
            self.h_layout.itemAt(i).widget().setParent(None)
        for tag in self.tags:
            self.add_tag_to_bar(tag)
        self.h_layout.addWidget(self.line_edit)
        self.line_edit.setFocus()
        self.comm.tags_updated.emit()

    def add_tag_to_bar(self, text):
        tag = QFrame()
        tag.setStyleSheet(
            """
            border:1px solid rgb(192, 192, 192); 
            border-radius: 4px;
            background-color: white;
            """
        )  # TODO: tag-specific color
        tag.setContentsMargins(2, 2, 2, 2)
        tag.setFixedHeight(28)
        hbox = QHBoxLayout()
        hbox.setContentsMargins(4, 4, 4, 4)
        hbox.setSpacing(10)
        tag.setLayout(hbox)
        label = QLabel(text)
        label.setStyleSheet("border:0px")
        label.setFixedHeight(16)
        hbox.addWidget(label)
        x_button = QPushButton("x")
        x_button.setFixedSize(20, 20)
        x_button.setStyleSheet("border:0px; font-weight:bold")
        x_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        x_button.clicked.connect(lambda _: self.delete_tag(text))
        hbox.addWidget(x_button)
        tag.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.h_layout.addWidget(tag)

    def delete_tag(self, tag_name):
        self.tags.remove(tag_name)
        self.refresh()


class FSViewer(QDockWidget):
    def __init__(self, parent, comm, db, *args, **kwargs) -> None:
        super().__init__("File System", parent, *args, **kwargs)
        self.comm = comm
        self.db = db
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self.fsmodel = FSModel(self)
        self.fsmodel.setRootPath(QDir.homePath())
        self.treeView = FSTreeView(self, comm)
        self.treeView.setModel(self.fsmodel)
        # self.treeView.header().moveSection(self.fsmodel.columnCount() - 1, 1)
        self.treeView.header().hideSection(1)  # size
        self.treeView.header().hideSection(2)  # type
        self.treeView.header().hideSection(3)  # date modified
        self.treeView.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.treeView.setAlternatingRowColors(True)
        self.w = QWidget(self)
        self.w.setLayout(QVBoxLayout(self.w))
        self.tagbar = TagBar(self, comm)
        self.w.layout().addWidget(self.tagbar)
        self.w.layout().addWidget(self.treeView)
        self.setWidget(self.w)

        self.connect_signals()

    def connect_signals(self):
        # Once a paper is selected, get its tags from the db
        self.comm.open_pdf.connect(self.get_paper_tags)

    def get_paper_tags(self, paper_path: str):
        tags = self.db.get_paper_tags(paper_path)
        self.tagbar.tags = tags
        self.tagbar.create_tags()

    def set_dir(self, path: str) -> None:
        """Update the filesystem TreeView to show the given directory path

        Args:
            path (str): directory path
        """
        p = pathlib.Path(path).resolve().as_posix()
        self.treeView.setRootIndex(self.fsmodel.index(p))
