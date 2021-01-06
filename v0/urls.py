from django.urls import path, include, re_path
from django.views.static import serve
from django.conf.urls.static import static
from django.conf.urls import url
from django.conf import settings
from . import views

urlpatterns = [
    path('', views.index, name='index'), # 主页
    path('get_table/', views.index_table, name='index_table'), 
    path('index_delete', views.index_delete, name='index_delete'),
    path('index_delete_with_local', views.index_delete_with_local, name='index_delete_with_local'),
    path('upload', views.upload, name='upload'), # 上传图片，已废弃
    path('upload_handle/', views.upload_handle, name='upload_handle'), # 处理上传的图片，已废弃
    path('batch_upload/', views.batch_upload, name='batch_upload'), #  上传图片，可批量上传
    path('batch_upload_handle/', views.batch_upload_handle, name='batch_upload_handle'), # 处理上传的图片

    path('process', views.process, name='process'), # 展示未处理的图片
    path('process_handle', views.process_handle, name='process_handle'), # 处理图片，包括分割+后处理
    path('process_progress', views.process_progress, name='process_progress'), # 负责和html模板沟通进度

    path('detail/<slug:name>/', views.detail, name='detail'), # 图片详情页
    path('detail_overlay/<slug:name>/', views.detail_overlay, name='detail_overlay'), # 图片详情页
    path('manual_DOI/<slug:name>/', views.manual_DOI, name='manual_DOI'),  # 展示手工调整DOI界面
    path('manual_DOI_handle', views.manual_DOI_handle, name='manual_DOI_handle'), # 处理手工调整DOI界面提交的信息
    path('manual_diameter/<slug:name>/', views.manual_diameter, name='manual_diameter'),  # 手工调整肿瘤最大径
    path('manual_diameter_handle', views.manual_diameter_handle, name='manual_diameter_handle'),
    re_path(r'^IMAGES/(?P<path>.*)$', serve, {'document_root': 'IMAGES'}), # 为了让html模板通过url的方式访问本地文件


    # re_path(r'^IMAGES/OriginalImages/(?P<path>.*)$', serve, {'document_root': 'IMAGES/OriginalImages'}),
    # re_path(r'^IMAGES/SegmentedImages/(?P<path>.*)$', serve, {'document_root': 'IMAGES/SegmentedImages'}),
    # re_path(r'^IMAGES/KeypointImages/(?P<path>.*)$', serve, {'document_root': 'IMAGES/KeypointImages'}),
    #path('images/<slug:name>/', views.detail, name='detail'), # show the dedail information of a image

]+static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)