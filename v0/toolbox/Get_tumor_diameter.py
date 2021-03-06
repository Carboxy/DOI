# -*- coding: utf-8 -*-
"""
Created on Fri Jul 31 16:13:03 2020

@author: Carboxy
"""


import cv2 as cv2
import numpy as np


def get_convex_hull(mask_dir):
    '''
    获取mask中肿瘤最大连通区域的凸包
    Args:
        mask_dir: mask的路径。
    Returns:
        hull (array sized [N,2]): 凸包的点构成的数组。
    '''

    mask = cv2.imread(mask_dir, cv2.IMREAD_GRAYSCALE) # (H, W)
    mask = np.where(mask>35, 0, mask) # 肿瘤处灰度值为29左右，设阈值为35
    _, mask = cv2.threshold(mask,20,255,cv2.THRESH_BINARY) # 肿瘤处为255，其他为0

    contours,hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    # 假设轮廓的点越多，所包含的面积越大，选取面积最大的绘制凸包
    contour_size = np.array([c.shape[0] for c in contours]) 
    main_contour_idx = np.argmax(contour_size)
    hull = cv2.convexHull(contours[main_contour_idx]) 
    hull = np.reshape(hull, (-1,2))

    return hull

def angel(x0, y0, x1, y1):
    '''
    计算向量 <x0, y0>和<x1, y1>的夹角的绝对值
    '''
    if x0==0 or y0==0: return 1
    v0_norm = np.sqrt(x0*x0+y0*y0)
    v1_norm = np.sqrt(x1*x1+y1*y1)
    dot_sum = abs(x0*x1 + y0*y1)
    cosin_abs = dot_sum/v0_norm/v1_norm
    return cosin_abs

def cross(hull, a, b, c):
    '''
    给定hull中点的序列a, b, c， 计算这三个点的围成的三角形面积，利用叉乘
    Args:
        hull (array sized [N,2]): 凸包的点构成的数组。
        a,b,c (int): 凸包中的点序列。
    Returns:
        S: 三角形的面积。
    '''
    y0 = hull[a,0]
    x0 = hull[a,1]
    y1 = hull[b,0]
    x1 = hull[b,1]
    y2 = hull[c,0]
    x2 = hull[c,1]    
    S = abs((x1-x0)*(y2-y0)-(x2-x0)*(y1-y0))
    return S   

def dist2(hull, a, b):
    '''
    给定hull中的两个点，计算它们距离的平方
    '''
    y0 = hull[a,0]
    x0 = hull[a,1]
    y1 = hull[b,0]
    x1 = hull[b,1]
    return (y0-y1)**2 + (x0-x1)**2

def get_convex_hull_diameter(hull, x0, y0, x1, y1):
    '''
    获取凸包直径和对应的两个点，使用旋转卡壳法。
    同时要求该直径与基准线（基准点所在的直线）的夹角小于10度。
    Args:
        hull (array sized [N,2]): 凸包的点构成的数组。
        x0, y0, x1, y1 (int): 2个基准点的坐标
    Returns:
        dia: 凸包的直径。
    '''

    q = 1
    dia = 0
    N = len(hull)
    hull = np.vstack((hull, hull[0, :]))
    q_dia = 0
    p_dia = 0

    for p in range(N):
        while (cross(hull, p+1, q+1, p) > cross(hull, p+1, q, p)):
            q = (q+1)%N
        dist2_1 = dist2(hull, p, q)
        dist2_2 = dist2(hull, p+1, q+1)
        if max(dist2_1, dist2_2) > dia:
            dia = max(dist2_1, dist2_2)
            if dist2_1> dist2_1:
                p_dia = p
                q_dia = q
            else:
                p_dia = p+1
                q_dia = q+1

    dia = np.sqrt(dist2(hull, p_dia, q_dia))
    # 计算夹角，如果符合要求，如果不负责要求，略微旋转该直径，使夹角符合要求
    dia_x0 = hull[p_dia,0]
    dia_y0 = hull[p_dia,1]
    dia_x1 = hull[q_dia,0]
    dia_y1 = hull[q_dia,1]
    cosin_abs = angel(dia_x0-dia_x1, dia_y0-dia_y1, x0-x1, y0-y1)
    # 大于10度， cos15° ≈ 0.966
    # 固定最大径的某个端点，调整另一个端点，因为有2个端点，所以要判断2组
    if cosin_abs < 0.9845:
        print('调整角度')
        dia_max = 0
        dia_x0 = hull[p_dia,0]
        dia_y0 = hull[p_dia,1]
        for i in range(N):

            dia_x1 = hull[i,0]
            dia_y1 = hull[i,1]
            tmp_cosin_abs = angel(dia_x0-dia_x1, dia_y0-dia_y1, x0-x1, y0-y1)
            if tmp_cosin_abs > 0.9845:
                dia_tmp = (dia_x0-dia_x1)**2 + (dia_y0-dia_y1)**2
                if dia_tmp > dia_max:
                    dia_max = dia_tmp
                    candidate_x1 = dia_x1
                    candidate_y1 = dia_y1

        point_flag = False # 标记固定哪个端点
        dia_x0 = hull[q_dia,0]
        dia_y0 = hull[q_dia,1]
        for i in range(N):
            dia_x1 = hull[i,0]
            dia_y1 = hull[i,1]
            tmp_cosin_abs = angel(dia_x0-dia_x1, dia_y0-dia_y1, x0-x1, y0-y1)
            if tmp_cosin_abs > 0.9845:
                dia_tmp = (dia_x0-dia_x1)**2 + (dia_y0-dia_y1)**2
                if dia_tmp > dia_max:
                    point_flag = True
                    dia_max = dia_tmp
                    candidate_x1 = dia_x1
                    candidate_y1 = dia_y1                    

        if not point_flag:
            dia_x0 = hull[p_dia,0]
            dia_y0 = hull[p_dia,1]

        return [dia_x0, dia_y0], [candidate_x1, candidate_y1], np.sqrt(dia_max)
    
    return hull[p_dia,:], hull[q_dia, :], dia

def get_tumor_diameter(mask_dir, x0, y0, x1, y1):
    hull = get_convex_hull(mask_dir)
    return get_convex_hull_diameter(hull, x0, y0, x1, y1)

if __name__ == '__main__':
    hull = get_convex_hull('D:/Academic/Django/projects/DOI/IMAGES/Masks/20190403083921.png')
    x0 = 4703
    y0 = 5488
    x1 = 4769
    y1= 3704
    p, q, dia = get_convex_hull_diameter(hull, x0, y0, x1, y1)
    print(p, ' ', q, ' ', dia)

    mask = cv2.imread('D:/Academic/Django/projects/DOI/IMAGES/Masks/20190403083921.png')
    mask = cv2.line(mask, (p[0], p[1]), (q[0], q[1]), (0,255,0), thickness=10)
    mask = cv2.line(mask, (x0, y0), (x1, y1), (255,255,255), thickness=10)
    cv2.imwrite('D:/Academic/Django/projects/DOI/IMAGES/Masks/sss.png', mask)