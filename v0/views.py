from django.shortcuts import render
from django.template import loader
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from .models import Images, Masks
from PIL import Image
from .toolbox.utils import tracker, get_foot_point, DateEncoder, cut_string_length, judge_tumor_stage
from .toolbox.Get_tumor_diameter import get_tumor_diameter
from .toolbox.filter.filters_apply import apply_color_filter_to_image
from .toolbox.tile.tile import Cutter
from .toolbox.key_map import KeyMap
from .segmentation.run_segmentation import Segmentation
from .segmentation.configs.config import config_django
import os, re, json, time, sys, math, torch
sys.path.append("..")

t = tracker() # Represents the progress of processing.

# Create your views here.
def index(request):
    '''
    负责展示主页
    '''
    image_list = Images.objects.order_by('-time')
    template = loader.get_template('table.html')
    context = {
        'image_list': image_list
    }
    return HttpResponse(template.render(context, request))

@csrf_exempt
def index_table(request):
    '''
    返回Bootstrap Table插件所需的数据，为展示主页服务
    '''
    image_list = Images.objects.order_by('-time')
    print('----------------')
    data = []
    for image in image_list:
        data.append({
            "name": image.name,
            "stage": image.tumor_stage,
            "depth": str(round(image.depth, 2)) + ' mm',
            "diameter": str(round(image.diameter, 2)) + ' mm',
            "comment": image.comment,
            "time": image.time,
            "description": cut_string_length(image.description, 15)
        })
    return HttpResponse(json.dumps(data, cls = DateEncoder))

@csrf_exempt
def index_delete(request):
    '''
    负责响应删除按钮，但只删除数据库中的图片，
    不删除本地实质图片内容
    '''
    to_delete_name = json.loads(request.body)
    for name in to_delete_name:
        image = Images.objects.get(name=name)
        image.delete()
    print(to_delete_name)
    return JsonResponse('成功删除', safe=False)


@csrf_exempt
def index_delete_with_local(request):
    '''
    负责响应删除按钮，但只删除数据库中的图片，
    同时删除本地实质图片内容
    '''
    to_delete_name = json.loads(request.body)
    for name in to_delete_name:
        image = Images.objects.get(name=name)
        image.delete()
    # TODO 
    # 删除本地图片

    print(to_delete_name)
    return JsonResponse('成功删除', safe=False)


def upload(request):
    '''
    负责展示上传图片的页面，已废弃
    '''
    return render(request, 'fileinput.html')

@csrf_exempt
def upload_handle(request):
    '''
    负责响应上传图片动作，已废弃
    '''
    if request.method == 'POST':
        # Save image to the database.
        image = request.FILES.get('image', '') 
        print(image)
        description = request.POST.get('description', '')

        image_name = image.name
        existed_image_num = Images.objects.filter(Q(name__startswith=image_name.split('.')[0])).count()

        if existed_image_num: # An image with a duplicate name already exists
            image_name_prefix = image_name.split('.')[0] # xxx
            image_name_postfix = image_name.split('.')[1] # png
            image_name = image_name_prefix + '(' + str(existed_image_num) + ').' + image_name_postfix # xxx(1).png

        # Save image.
        imagefile = '%s/IMAGES/Images/%s'%(settings.BASE_DIR,image_name)
        with open(imagefile, 'wb') as f:
            for c in image.chunks():
                f.write(c)
                
        # Get height and width of image.
        pil_img = Image.open(imagefile)
        width = pil_img.size[0]
        height = pil_img.size[1]

        # Save image into database
        original_image = Images.objects.create(
            image = '/IMAGES/Images/%s' % image_name,
            description = description,
            name = image_name.split('.')[0],
            postfix = image_name.split('.')[1],
            height = height,
            width = width,
            depth = 0,
        )
        original_image.save()


        mask = Masks.objects.create(related_image=original_image, 
                                    name=image_name.split('.')[0],
                                    height = height,
                                    width = width)
        mask.save()
        imagefile = '%s/IMAGES/Masks/%s'%(settings.BASE_DIR,image_name)
        with open(imagefile, 'wb') as f:
            for c in image.chunks():
                f.write(c)



        #return render(request, 'import_success.html')
        return JsonResponse({'success':0})
    return HttpResponse('未上传成功')

def batch_upload(request):
    '''
    负责呈现上传图片页面
    '''
    return render(request, 'batch_fileinput.html')

@csrf_exempt
def batch_upload_handle(request):
    '''
    负责响应上传图片操作
    '''
    image_names = json.loads(request.body)

    track_total = 2*len(image_names)  # 进度条总的step，每张图片细分为 2 个step
    track_count = 0 # 实时进度
    t.refresh(track_count) 
    track_count += 1
    for i,image_name in enumerate(image_names):

        # 当上传图片的名字已存在数据库中时，进行重命名操作
        #existed_image_num = Images.objects.filter(Q(name__startswith=image_name.split('.')[0])).count()
        existed_image_num = Images.objects.filter(origin_name=image_names).count()
        if existed_image_num: # An image with a duplicate name already exists
            image_name_prefix = image_name.split('.')[0] # 名称前缀，不包括扩展名，xxx
            image_name_postfix = image_name.split('.')[1] # png
            image_name_origin = image_name
            image_name = image_name_prefix + '-' + str(existed_image_num) + '.' + image_name_postfix # xxx(1).png
        else:
            image_name_origin = image_name

        # Step 1. 得到缩略图保存在媒体库文件夹/IMAGES/下
        # 值得注意的是，原来应该是从request中获取用户上传的image，
        # 但是我们这个任务比较特殊，一是image都在本地，二是image很大，上传较慢，
        # 所以这里选择了只从request获取文件名，然后直接从预设的image路径scaledown8_png/中加载图片
        img_path = '%s/v0/segmentation/scaledown8_png/%s'%(settings.BASE_DIR,image_name_origin)
        #img_path = 'D:\\Academic\\Django\\projects\DOI\\v0\\segmentation\\scaledown8_png\\%s'%(image_name_origin)
        image = Image.open(img_path)
        w, h = image.size
        w_scaled = 700 # 缩略图固定宽度
        h_scaled = round(w_scaled/w*h)
        image_thumbnail = image.resize((w_scaled, h_scaled), Image.ANTIALIAS)
        thumbnail_path = '%s/IMAGES/Images/%s'%(settings.BASE_DIR,image_name) 
        image_thumbnail.save(thumbnail_path) # 保存缩略图

        t.refresh(track_count) # 更新进度
        track_count += 1 


        # Step 2：保存图片信息至数据库
        # image_name 形式为 xxx.png
        # name 形式为 xxx
        original_image = Images.objects.create(
            image = '/IMAGES/Images/%s' % image_name,
            description = ' ',
            origin_name = image_name_origin,
            name = image_name.split('.')[0],
            postfix = image_name.split('.')[1],
            height = h_scaled,
            width = w_scaled,
            depth = 0,
            h = h,
            w = w,
        )
        original_image.save() 

        # 初始化图片对应的mask信息，并保存至数据库
        mask = Masks.objects.create(related_image=original_image, 
                                    name=image_name.split('.')[0],
                                    height = h,
                                    width = w)
        mask.save()
        # At the beginning we have no masks, so let's substitute original_image for mask.
        mask_dir = '%s/IMAGES/Masks/%s'%(settings.BASE_DIR,image_name)
        image_thumbnail.save(mask_dir)

        t.refresh(track_count) # 更新进度
        track_count += 1 

        print('----------------------')
        print('Upload progress: %d/%d'%(i+1, len(image_names)))
        print('----------------------')


    return HttpResponse(json.dumps({
            "status":1
            #"image_num": len(selected_images)
            }))
def process(request):
    '''
    image.Is_processed 指示该图片是否已处理（过滤+切片+分割+后处理）
    然后在处理页面上列出未被处理的图片
    '''
    image_list = Images.objects.order_by('-time')
    unprocessed_image_list = []
    for image in image_list:
        if image.Is_processed == False:
            unprocessed_image_list.append(image)

    template = loader.get_template('process.html')
    context = {
        'image_list': unprocessed_image_list
    }
    print('---------------------------')
    print('Unprocessed images: ')
    print(unprocessed_image_list)
    print('---------------------------')
    return HttpResponse(template.render(context, request))


@csrf_exempt
def process_handle(request):
    '''
    对于用户挑选的需要处理的图片，逐张进行操作：
    1. 分割
    2. 后处理，包括测量DOI和肿瘤最长径
    3. 更新数据库的信息
    '''
    t.refresh(0)
    if request.method == 'POST':
        selected_images = json.loads(request.body)
        print('---------------------------')
        print('The following images will be processed: ', selected_images)
        print('---------------------------')
        # Track the progress of processing data.
        track_total = 3*len(selected_images) # 进度条的step，每张图片细分为3个step
        track_count = 0

        # initialize segmentation network
        seg_worker = Segmentation(config_django, selected_images)
        t.refresh(track_count)
        track_count += 1

        for i,selected_image in enumerate(selected_images):
            print(selected_image)
            image = Images.objects.get(name=selected_image)
            origin_name = image.origin_name # 对应本地文件
            image_name = selected_image + '.' + image.postfix # 对应数据库中的图片名

            # Step 1: 过滤
            #item_folder = '%s/v0/segmentation/scaledown8_png/'%(settings.BASE_DIR)
            item_folder = 'D:/Academic/Medical Image Process/OSCC Data/5x_png/'
            filtered_dir = '%s/IMAGES/filtered_png/'%(settings.BASE_DIR)
            filted_mask_dir = '%s/IMAGES/filtered_mask/'%(settings.BASE_DIR)
            pil_image = apply_color_filter_to_image(origin_name, image_name, item_folder, filtered_dir, filted_mask_dir, hole_size=2000, object_size=3000)

            # Step 2: 切patch
            slide_list = [selected_image]
            sample_type = 'seg'
            patch_size = 1600
            overlap = 400
            filter_rate = 0.10
            cutter = Cutter(slide_list, [pil_image], sample_type=sample_type)
            tile_info, samples_pil, samples = cutter.sample_and_store_patches_png(patch_size, overlap, filter_rate)

            t.refresh(track_count)
            track_count += 1

            # Step 3: 分割
            size = tile_info['size']
            tiles = tile_info['tiles']
            step = tile_info['step']
            info = dict()
            info[selected_image] = {'size':size, 'tiles': tiles, 'step': step}
            seg_worker.update_dataset(info)
            seg_worker.run_segmentation(selected_image, samples_pil, samples)

            t.refresh(track_count)
            track_count += 1

            # Step 4: 得到测量DOI所需的3个关键点，并计算DOI
            image = Images.objects.get(name=selected_image)
            mask = Masks.objects.get(related_image=image)
            mask_dir = '%s/IMAGES/Masks/%s%s'%(settings.BASE_DIR,selected_image,'.png')

            mask_keymap = KeyMap(mask_dir)
            keypoints_base = mask_keymap.search_keypoint(alpha=2) # 基准线的两个端点
            keypoints_top = mask_keymap.key_point_tumor #浸润最深处的点
            doi = mask_keymap.doi  # based on pixels
            height, width = mask_keymap.get_mask_size()

            mask.keypoint_x0 = keypoints_base[0][0]
            mask.keypoint_y0 = keypoints_base[0][1]
            mask.keypoint_x1 = keypoints_base[1][0]
            mask.keypoint_y1 = keypoints_base[1][1]
            mask.keypoint_xt = keypoints_top[0]
            mask.keypoint_yt = keypoints_top[1]
            xf, yf = get_foot_point(keypoints_base, keypoints_top)
            mask.keypoint_xf = xf
            mask.keypoint_yf = yf

            mask.width = width
            mask.height = height

            mask.save()

            scale = mask.scale
            doi = doi * scale /1000 # based on mm
            image.depth = doi
            #image.Is_processed = True
            image.save()

            # Step 5: 得到肿瘤最长径所需的2个关键点，并计算最长径
            #mask_dir = '%s/IMAGES/Masks/%s%s'%(settings.BASE_DIR,selected_image,'.png')
            point0, point1, diameter = get_tumor_diameter(mask_dir, 
            keypoints_base[0][0], keypoints_base[0][1], keypoints_base[1][0], keypoints_base[1][1])
            #print(diameter)
            diameter = diameter * scale /1000 # based on pixels -> based on mm
            image.diameter = diameter
            tumor_stage = judge_tumor_stage(diameter, doi) # one from 'T1' 'T2' 'T3' 'UC'
            image.tumor_stage = tumor_stage
            image.Is_processed = True
            image.save()

            mask.dia_x0 = point0[0]
            mask.dia_y0 = point0[1]
            mask.dia_x1 = point1[0]
            mask.dia_y1 = point1[1]            
            mask.save()

            t.refresh(track_count)
            track_count += 1

            print('----------------------')
            print('Process progress: %d/%d'%(i+1, len(selected_images)))
            print('----------------------')
            torch.cuda.empty_cache()

        del seg_worker
        torch.cuda.empty_cache()

        return HttpResponse(json.dumps({
            "status":selected_image
            #"image_num": len(selected_images)
        }))
    return HttpResponse('未处理')
@csrf_exempt
def process_progress(request):
    return JsonResponse(t.get_value(), safe=False)

def detail(request, name):
    '''
    图片详情页，双图模式
    '''
    # print(name)
    # print('+++++++++++++')
    image = Images.objects.get(name=name) 
    mask = Masks.objects.get(related_image=image)

    objs = Images.objects.all().order_by('time')
    #next_image = objs.filter(time__gt=image.time).first()
    next_image = objs.filter(time__lt=image.time).last()
    last_image = objs.filter(time__gt=image.time).first()

    height = mask.height
    width = mask.width


    keypoints = [mask.keypoint_x0,
                 mask.keypoint_y0,
                 mask.keypoint_x1,
                 mask.keypoint_y1,
                 mask.keypoint_xt,
                 mask.keypoint_yt,
                 mask.keypoint_xf,
                 mask.keypoint_yf]
    diameter_points = [mask.dia_x0,
                       mask.dia_y0,
                       mask.dia_x1,
                       mask.dia_y1,
    ]

    context = {
        'name': name,
        'next_image': next_image,
        'last_image': last_image,
        'image': image,
        'time': image.time,
        'depth': round(image.depth, 2),
        'diameter': round(image.diameter, 2),
        'keypoints': keypoints,
        'diameter_points': diameter_points,
        'w': width,
        'h': height,
        
    }

    print('---------------------------------')
    print('Show the detail of image.')
    print('Two images mode.')
    print('current image:', image)
    print('last image: ', last_image)
    print('next image: ', next_image)
    print('---------------------------------')
    #print(objs)

    template = loader.get_template('detail.html')

    # 图片详情页更新信息并保存后，以下代码片段处理更新信息
    if request.method == 'POST':
        tumor_stage = request.POST.get('tumor_stage','')
        comment = request.POST.get('comment','')
        description = request.POST.get('description','')

        image.tumor_stage = tumor_stage
        image.comment = comment
        image.description = description
        image.save()

        context = {
        'name': name,
        'next_image': next_image,
        'last_image': last_image, 
        'image': image,
        'depth': round(image.depth, 2),
        'diameter': round(image.diameter, 2),
        'keypoints': keypoints,
        'diameter_points': diameter_points,
        'w': width,
        'h': height,
        }
        return HttpResponse(template.render(context, request))
    return HttpResponse(template.render(context, request))

def detail_overlay(request, name):
    '''
    展示图片详情，叠加模式
    '''
    # print(name)
    # print('+++++++++++++')
    image = Images.objects.get(name=name)
    mask = Masks.objects.get(related_image=image)

    objs = Images.objects.all().order_by('time')
    #next_image = objs.filter(time__gt=image.time).first()
    next_image = objs.filter(time__lt=image.time).last()
    last_image = objs.filter(time__gt=image.time).first()

    height = mask.height
    width = mask.width

    keypoints = [mask.keypoint_x0,
                 mask.keypoint_y0,
                 mask.keypoint_x1,
                 mask.keypoint_y1,
                 mask.keypoint_xt,
                 mask.keypoint_yt,
                 mask.keypoint_xf,
                 mask.keypoint_yf]
    diameter_points = [mask.dia_x0,
                       mask.dia_y0,
                       mask.dia_x1,
                       mask.dia_y1,
    ]

    context = {
        'name': name,
        'next_image': next_image,
        'last_image': last_image,
        'image': image,
        'time': image.time,
        'depth': round(image.depth, 2),
        'diameter': round(image.diameter, 2),
        'keypoints': keypoints,
        'diameter_points': diameter_points,
        'w': width,
        'h': height,
        
    }

    print('---------------------------------')
    print('Show the detail of image.')
    print('Overlay mode.')
    # print('keypoints: ', keypoints)
    print('current image:', image)
    print('last image: ', last_image)
    print('next image: ', next_image)
    print('---------------------------------')
    #print(objs)

    template = loader.get_template('detail_overlay.html')
    if request.method == 'POST':
        tumor_stage = request.POST.get('tumor_stage','')
        comment = request.POST.get('comment','')
        description = request.POST.get('description','')

        image.tumor_stage = tumor_stage
        image.comment = comment
        image.description = description
        image.save()

        context = {
        'name': name,
        'next_image': next_image,
        'last_image': last_image, 
        'image': image,
        'depth': round(image.depth, 2),
        'diameter': round(image.diameter, 2),
        'keypoints': keypoints,
        'diameter_points': diameter_points,
        'w': width,
        'h': height,
        }
        return HttpResponse(template.render(context, request))
    return HttpResponse(template.render(context, request))

def manual_DOI(request, name):
    image = Images.objects.get(name=name)
    mask  = Masks.objects.get(related_image=image)
    height = mask.height
    width = mask.width
    context = {
        'name': name,
        'h': height,
        'w': width,
        
    }
    print('---------------------------------')
    print('Start manual annotating the DOI.')
    # print('image height: %d'%height)
    # print('image width: %d'%width)
    print('image name: ', name)
    print('---------------------------------')
    template = loader.get_template('manual_DOI.html')
    return HttpResponse(template.render(context, request))


@csrf_exempt
def manual_DOI_handle(request):
    if request.method == 'POST':
        keypoints = json.loads(request.body)
        name = keypoints['name']
        x0 = keypoints['x0'] # (x0, y0), (x1, y1) 是基准线的2个点
        y0 = keypoints['y0']
        x1 = keypoints['x1']
        y1 = keypoints['y1']
        xt = keypoints['xt'] # (xt, yt)是侵袭最深的点
        yt = keypoints['yt']
        xf = keypoints['xf'] # (xf, yf)是侵袭最深点向基准线作的垂足
        yf = keypoints['yf']
        scaled_height = keypoints['scaled_h'] # 网页上的图片尺寸和实际尺寸有一个缩放关系
        scaled_width = keypoints['scaled_w']

        image = Images.objects.get(name=name)
        mask = Masks.objects.get(related_image=image)
        height = mask.height
        width = mask.width 

        mask.keypoint_x0 = x0*width/scaled_width
        mask.keypoint_y0 = y0*height/scaled_height
        mask.keypoint_x1 = x1*width/scaled_width
        mask.keypoint_y1 = y1*height/scaled_height
        mask.keypoint_xt = xt*width/scaled_width
        mask.keypoint_yt = yt*height/scaled_height
        mask.keypoint_xf = xf*width/scaled_width
        mask.keypoint_yf = yf*height/scaled_height

        mask.save()

        scale = mask.scale # 一个像素对应的实际物理尺寸
        image.depth = math.sqrt((mask.keypoint_yf-mask.keypoint_yt)**2+\
            (mask.keypoint_xf-mask.keypoint_xt)**2) * scale / 1000

        image.save()
        print('---------------------------------')
        print('Manual annotating the DOI successed!')
        # print('scaled_height: %d, scaled_width: %d'%(scaled_height, scaled_width))
        # print('height: %d, width: %d'%(height, width))
        # print('Based on sacled size, (x0, y0), (x1, y1), (xf, yf) = ')
        # print('(',x0,', ',y0, '), (', x1,', ',y1, '), (', xf,', ',yf, ')')
        print('image name: ', name)
        print('DOI = %.3f mm'%image.depth)
        print('---------------------------------')
        #return HttpResponse(keypoints)
        return HttpResponse(json.dumps({
            "status":1
        }))
    return render(request, 'manual_DOI.html')

def manual_diameter(request, name):
    image = Images.objects.get(name=name)
    mask  = Masks.objects.get(related_image=image)
    height = mask.height
    width = mask.width

    context = {
        'name': name,
        'h': height,
        'w': width,
        
    }
    print('---------------------------------')
    print('Start manual annotating the diameter.')
    # print('image height: %d'%height)
    # print('image width: %d'%width)
    print('image name: ', name)
    print('---------------------------------')
    template = loader.get_template('manual_diameter.html')
    return HttpResponse(template.render(context, request))

@csrf_exempt
def manual_diameter_handle(request):
    if request.method == 'POST':
        diameter = json.loads(request.body)
        name = diameter['name']
        x0 = diameter['x0']
        y0 = diameter['y0']
        x1 = diameter['x1']
        y1 = diameter['y1']
        scaled_height = diameter['scaled_h']
        scaled_width = diameter['scaled_w']
        print(x0,',',y0,',',name)

        image = Images.objects.get(name=name)
        mask = Masks.objects.get(related_image=image)
        height = mask.height
        width = mask.width

        mask.dia_x0 = x0*width/scaled_width
        mask.dia_y0 = y0*height/scaled_height
        mask.dia_x1 = x1*width/scaled_width
        mask.dia_y1 = y1*height/scaled_height


        mask.save()

        scale = mask.scale
        image.diameter = math.sqrt((mask.dia_x1-mask.dia_x0)**2+\
            (mask.dia_y1-mask.dia_y0)**2) * scale / 1000

        image.save()
        print('---------------------------------')
        print('Manual annotating the diameter successed!')
        print('image name: ', name)
        # print('scaled_height: %d, scaled_width: %d'%(scaled_height, scaled_width))
        # print('height: %d, width: %d'%(height, width))
        print('Diameter = %.3f mm'%image.diameter)
        print('---------------------------------')
        #return HttpResponse(keypoints)
        return HttpResponse(json.dumps({
            "status":1
        }))
    return render(request, 'manual_diameter.html')


def process_data(request):
    for i in range(100):
        t.refresh(i)
        time.sleep(1)
    
    return JsonResponse('开始处理数据')


